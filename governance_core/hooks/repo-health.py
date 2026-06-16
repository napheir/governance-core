"""Claude Code PostToolUse hook: repo-health.py

Audit hook that checks for git repo damage AFTER each Bash invocation.
Detects suspicious post-conditions even when the command itself slipped
through PreToolUse (catches indirect destruction via scripts -- see
proposals/harden_destructive_command_guard.md sec.2.4 + sec.1 item 10).

Behavior:
  1. On first invocation per (session, repo), capture pre-state to
     ~/.claude/cache/repo_health_<sha256(repo_path)[:12]>.json:
       - .git/HEAD exists
       - rev-parse HEAD value
       - branch + remote-ref count (for-each-ref)
  2. After each Bash call, re-read state. If any damage signal:
       - .git dir disappeared / HEAD missing
       - HEAD moved backward (merge-base --is-ancestor fails)
       - branch count dropped >= 2 in single tool call
     append alert to <repo>/audit/repo_health_alerts.jsonl AND emit a
     [REPO-HEALTH ALERT] line on stderr (visible in CC UI).
  3. NON-BLOCKING: always exit 0. Pure audit/observability layer.
     Blocking would be too risky (false positives on legitimate merges,
     rebases, GC). Pair with PreToolUse deny layers + human review SLA.
  4. Skip read-only commands (git status / diff / log / show, pytest,
     ls, etc.) -- they can't move git state.
  5. Performance budget: < 200ms per invocation. Cached pre-state in
     memory across same session.

Cache key choice (sec.8 Q3): hash(repo_path) not git remote URL --
all 5 trade-agent clones share the same remote URL but have distinct
working trees, so URL-keying loses resolution.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


# Commands that cannot mutate git state -- skip the post-state diff.
READ_ONLY_PATTERNS = [
    r"^\s*git\s+(status|diff|log|show|reflog|rev-parse|describe|fsck|count-objects|for-each-ref|cat-file)\b",
    r"^\s*git\s+branch\s*(-l|-r|-a|--list|$)",
    r"^\s*git\s+remote\s+(-v|show|$)",
    r"^\s*git\s+config\s+--get\b",
    r"^\s*python\s+-m\s+pytest\b",
    r"^\s*python\s+-m\s+(unittest|coverage)\b",
    r"^\s*pytest\b",
    r"^\s*ls\b",
    r"^\s*dir\b",
    r"^\s*cat\s+",
    r"^\s*head\s+",
    r"^\s*tail\s+",
    r"^\s*grep\b",
    r"^\s*rg\b",
    r"^\s*find\s+.*-name\b",
    r"^\s*echo\b",
    r"^\s*pwd\b",
    r"^\s*which\b",
    r"^\s*type\b",
    r"^\s*wc\s+",
]


def is_read_only(command: str) -> bool:
    for pattern in READ_ONLY_PATTERNS:
        if re.match(pattern, command):
            return True
    return False


def cache_path_for_repo(repo_path: str) -> Path:
    """Cache key by repo path hash. See module docstring sec.8 Q3."""
    digest = hashlib.sha256(repo_path.encode("utf-8")).hexdigest()[:12]
    return Path.home() / ".claude" / "cache" / f"repo_health_{digest}.json"


def find_repo_root(start: Path) -> Path | None:
    """Walk up from start looking for .git directory. None if not in a repo."""
    cur = start.resolve()
    while True:
        if (cur / ".git").exists():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def capture_state(repo_root: Path) -> dict:
    """Capture current git state. Empty dict on error (don't crash CC)."""
    state: dict = {"timestamp": time.time()}
    try:
        head_ref_path = repo_root / ".git" / "HEAD"
        state["git_dir_exists"] = (repo_root / ".git").exists()
        state["head_file_exists"] = head_ref_path.exists()
    except OSError:
        state["git_dir_exists"] = False
        state["head_file_exists"] = False
        return state

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            state["head_sha"] = result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        pass

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "for-each-ref",
             "--format=%(refname)", "refs/heads", "refs/remotes"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            refs = [line for line in result.stdout.splitlines() if line.strip()]
            state["ref_count"] = len(refs)
            state["refs"] = sorted(refs)
    except (subprocess.SubprocessError, OSError):
        pass

    return state


def detect_damage(pre: dict, post: dict, repo_root: Path) -> list[str]:
    """Compare pre/post state, return list of damage signal strings."""
    signals: list[str] = []

    # .git dir disappeared
    if pre.get("git_dir_exists") and not post.get("git_dir_exists"):
        signals.append(".git directory disappeared")
    if pre.get("head_file_exists") and not post.get("head_file_exists"):
        signals.append(".git/HEAD missing")

    # HEAD backward (rewrite or reset)
    pre_sha = pre.get("head_sha")
    post_sha = post.get("head_sha")
    if pre_sha and post_sha and pre_sha != post_sha:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo_root), "merge-base",
                 "--is-ancestor", pre_sha, post_sha],
                capture_output=True, timeout=5,
            )
            if result.returncode != 0:
                signals.append(
                    f"HEAD moved backward / sideways: {pre_sha[:7]} -> "
                    f"{post_sha[:7]} (not ancestor)"
                )
        except (subprocess.SubprocessError, OSError):
            pass

    # Branch / ref count drop >= 2 (one drop is normal; two+ is suspicious)
    pre_count = pre.get("ref_count", 0)
    post_count = post.get("ref_count", 0)
    if pre_count and post_count and pre_count - post_count >= 2:
        pre_refs = set(pre.get("refs", []))
        post_refs = set(post.get("refs", []))
        gone = sorted(pre_refs - post_refs)
        signals.append(
            f"ref count dropped {pre_count} -> {post_count}; "
            f"missing: {', '.join(gone[:5])}"
        )

    return signals


def append_alert(repo_root: Path, command: str, signals: list[str]) -> None:
    """Append a single JSON line to <repo>/audit/repo_health_alerts.jsonl."""
    audit_dir = repo_root / "audit"
    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    record = {
        "timestamp": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "command": command[:500],
        "signals": signals,
        "cwd": os.getcwd(),
    }
    try:
        with open(audit_dir / "repo_health_alerts.jsonl",
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def main() -> None:
    # Always exit 0 -- non-blocking audit hook.
    try:
        hook_input = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Bash":
        sys.exit(0)

    command = hook_input.get("tool_input", {}).get("command", "")
    if not command or is_read_only(command):
        sys.exit(0)

    cwd = Path(os.getcwd())
    repo_root = find_repo_root(cwd)
    if repo_root is None:
        sys.exit(0)  # not in a git repo -- nothing to audit

    cache_file = cache_path_for_repo(str(repo_root))
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    # Read pre-state (if exists), then capture post-state
    pre_state: dict = {}
    if cache_file.exists():
        try:
            pre_state = json.loads(cache_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pre_state = {}

    post_state = capture_state(repo_root)

    # If we have a meaningful pre-state, compare
    if pre_state.get("head_sha") or pre_state.get("ref_count"):
        signals = detect_damage(pre_state, post_state, repo_root)
        if signals:
            sys.stderr.write(
                f"[REPO-HEALTH ALERT] command may have damaged repo at "
                f"{repo_root.name}:\n"
            )
            for s in signals:
                sys.stderr.write(f"  - {s}\n")
            append_alert(repo_root, command, signals)

            # Phase C of proposal harden_indirect_attack_paths:
            # write alarm file consumed by session-boundary-guard at next
            # PreToolUse Bash. The boundary guard reads this file and
            # exit 2 with a clear-instructions message until user
            # manually removes the alarm. This converts repo-health from
            # pure audit (post-damage) to "audit + brake" (post-damage
            # but blocks subsequent actions until user inspection).
            alarm_path = Path.home() / ".claude" / "cache" / "repo_health_alarm.json"
            try:
                alarm_path.parent.mkdir(parents=True, exist_ok=True)
                alarm_record = {
                    "ts": time.time(),
                    "iso": time.strftime("%Y-%m-%dT%H:%M:%S",
                                         time.localtime()),
                    "repo_root": str(repo_root),
                    "command_preview": command[:500],
                    "signals": signals,
                    "cwd": os.getcwd(),
                }
                alarm_path.write_text(
                    json.dumps(alarm_record, ensure_ascii=False),
                    encoding="utf-8",
                )
                sys.stderr.write(
                    f"\n  [REPO-HEALTH] alarm written to {alarm_path}\n"
                    f"  Subsequent Bash/Edit/Write will be blocked until\n"
                    f"  the alarm file is manually removed:\n"
                    f"    rm '{alarm_path}'\n"
                    f"  (Run from PowerShell terminal if CC blocks the rm.)\n"
                )
            except OSError:
                pass

    # Update cache for next call
    try:
        cache_file.write_text(
            json.dumps(post_state, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
