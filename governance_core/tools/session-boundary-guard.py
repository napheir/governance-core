"""Claude Code PreToolUse hook: session-boundary-guard.py

User-global hook that blocks Bash / Edit / Write tool calls whose target
path falls outside the session's boundary. Implements
proposals/project_boundary_guard_for_extra_project_writes.md (v2).

Boundary discovery: imports from peer derive_session_boundary.py if
present; falls back to inline-equivalent when run as a single-file
deployment under ~/.claude/hooks/. The bootstrap installer copies BOTH
files into ~/.claude/hooks/ so import works there.

Behavior:
  0. Skip non-Bash/Edit/Write tools (fast exit 0).
  1. Compute boundary from os.getcwd() using
     derive_session_boundary.derive_boundary().
  2. Honor CLAUDE_BOUNDARY_OVERRIDE=1 env var (must be set BEFORE Claude
     Code launch -- env-var-inheritance is the validation; we cannot
     reliably detect in-process injection on all platforms, but the LLM
     also cannot easily inject into a sibling hook process).
  3. Critical paths (~/.ssh, ~/.aws, ~/.docker, Windows system dirs,
     ~/.claude/settings.json) are ALWAYS blocked, even with override.
  4. Edit / Write: check tool_input.file_path against boundary.
  5. Bash: extract candidate write paths from the command via heuristics
     (cd targets, redirects, mkdir / cp / mv / rm / git init / etc.) and
     check each.

Exit codes:
  0 = allow / delegate to next hook
  2 = block

When override is consumed, append to
~/.claude/cache/boundary_override_audit.jsonl so usage stays auditable.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Try to import the helper from the same dir (peer file). When deployed
# under ~/.claude/hooks/ the bootstrap installer drops derive_session_
# boundary.py alongside this script and adds the dir to sys.path here.
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from derive_session_boundary import (  # type: ignore
        Boundary,
        derive_boundary,
        is_inside_boundary,
    )
except ImportError as exc:
    # Fail-OPEN here is intentional: if helper is missing the hook itself
    # is broken, and we should not silently block every write. Surface
    # error to stderr (visible in CC) so the user fixes the install.
    sys.stderr.write(
        f"[BOUNDARY GUARD] FATAL: derive_session_boundary helper missing "
        f"({exc}). Install incomplete. Skipping enforcement.\n"
    )
    sys.exit(0)


# Paths that are NEVER writable, regardless of session boundary or
# override flag. Stored as substring matches against the resolved
# absolute path (with forward slashes on Windows for portability).
CRITICAL_PATH_PATTERNS = [
    # Windows system dirs
    "/Windows/",
    "/Program Files/",
    "/Program Files (x86)/",
    "/ProgramData/",
    # Credential / key stores (cross-platform; ~/ resolves to user home)
    "/.ssh/",
    "/.aws/",
    "/.gcp/",
    "/.docker/config",
    "/.kube/",
    "/.gnupg/",
    "/.azure/",
    # Hook-config self-modification prevention
    "/.claude/settings.json",
    "/.claude/settings.local.json",
]

# Bash command patterns we extract write-target candidates from.
# Each entry is (regex, group_index_for_path, label).
#
# Design intent: only match patterns where a path has clear WRITE
# semantics. The catch-all "absolute path anywhere" rule was removed
# 2026-05-01 because it false-positive'd on read-only commands like
# `ls /c/Users/naphe/.../agent-rules/` and `cat <abs-path>`. Read-only
# commands are now skipped wholesale via READ_ONLY_BASH_PATTERNS below.
BASH_PATH_PATTERNS = [
    # cd PATH (... && rest)  -> PATH (state change; if relative path
    # writes follow, they resolve relative to PATH)
    (re.compile(r"\bcd\s+([^\s&|;<>]+)"), 1, "cd"),
    # mkdir [-p] PATH
    (re.compile(r"\bmkdir(?:\s+-\w+)*\s+([^\s&|;<>]+)"), 1, "mkdir"),
    # > PATH or >> PATH (redirect)
    (re.compile(r">>?\s*([^\s&|;<>]+)"), 1, "redirect"),
    # cp [-flags] SRC DEST  (catch DEST = group 1 of last \S+)
    (re.compile(r"\bcp\s+(?:-\w+\s+)*\S+\s+([^\s&|;<>]+)"), 1, "cp"),
    # mv [-flags] SRC DEST
    (re.compile(r"\bmv\s+(?:-\w+\s+)*\S+\s+([^\s&|;<>]+)"), 1, "mv"),
    # rm [-flags] PATH
    (re.compile(r"\brm\s+(?:-\w+\s+)*([^\s&|;<>]+)"), 1, "rm"),
    # git init [PATH]
    (re.compile(r"\bgit\s+init\s+([^\s&|;<>]+)"), 1, "git init"),
    # git clone <url> PATH
    (re.compile(r"\bgit\s+clone\s+\S+\s+([^\s&|;<>]+)"), 1, "git clone dest"),
    # PowerShell Set-Content / Out-File: -Path X or positional X.
    # Require \s+ between cmdlet and path so '...Out-File ' + path is
    # captured (the original missing-\s+ form failed when path follows
    # immediately after a quoted command in pwsh -Command). Match either
    # '-Path/-FilePath FILE' or positional first arg.
    (re.compile(r"\bSet-Content\b\s+(?:-Path\s+)?[\"']?([^\s\"'&|;<>]+)", re.IGNORECASE), 1, "Set-Content"),
    (re.compile(r"\bOut-File\b\s+(?:-FilePath\s+)?[\"']?([^\s\"'&|;<>]+)", re.IGNORECASE), 1, "Out-File"),
    # gh repo create: triggers git init in cwd implicitly. cwd check is
    # implicit -- if cwd is outside boundary at the moment of invocation,
    # the *cd* extractor catches it; if the user uses `gh repo create
    # --source <PATH>` we catch the source path here.
    (re.compile(r"\bgh\s+repo\s+create\b.*?--source\s+([^\s&|;<>]+)"), 1, "gh repo create"),
    # Phase A (proposal harden_indirect_attack_paths): extend coverage
    # to indirect verbs that also write but were not in V1 list.
    # sed -i / -i.bak FILE -- in-place edit. The flag may also be
    # combined like -ie.bak. Match the FILE as the LAST positional arg.
    (re.compile(r"\bsed\s+(?:-\w*\s+)*-i\w*[\w.]*\s+(?:-\w+\s+)*\S+\s+([^\s&|;<>]+)"), 1, "sed -i"),
    # awk -i inplace ... FILE
    (re.compile(r"\bawk\s+(?:-\w+\s+)*-i\s+inplace\b.*?([^\s&|;<>]+)$",
                re.MULTILINE), 1, "awk -i inplace"),
    # tee FILE / tee -a FILE -- writes stdin to FILE
    (re.compile(r"\btee\s+(?:-\w+\s+)*([^\s&|;<>]+)"), 1, "tee"),
    # truncate -s SIZE FILE -- shrink/grow file (ZERO truncates content)
    (re.compile(r"\btruncate\s+(?:-\w+\s+)*-s\s+\S+\s+([^\s&|;<>]+)"), 1, "truncate"),
    # python -c "...open('FILE', 'w')..." -- inline script writes file.
    # Catches obvious form; defeated by string concat / variable
    # substitution (proposal accepts that limitation).
    (re.compile(r"\bpython\s+-c\s+[\"'].*?\bopen\s*\(\s*[\"']([^\"'<>]+)[\"']\s*,\s*[\"']w",
                re.IGNORECASE | re.DOTALL), 1, "python -c open(w)"),
    # Note: pwsh -Command "...Out-File FILE..." is caught transparently
    # by the Out-File regex above, which scans the full command string.
    # PowerShell variable-indirection destructive forms (e.g. `& $cmd
    # -Recurse` where $cmd is built from string concat) are NOT caught
    # at this layer because they are pathless. Phase B
    # (edit-write-guard destructive content scan) covers that vector
    # by scanning Write/Edit content before the script reaches disk.
]


# Bash commands that cannot write to disk -- skip path extraction
# entirely. Avoids false positives on `ls /abs/path` (read-only) and
# similar. Patterns are anchored to start of command (^\s*). Compound
# commands like `ls X && rm Y` will NOT be caught by this anchor -- they
# fall through to BASH_PATH_PATTERNS where the destructive subexpr is
# matched.
READ_ONLY_BASH_PATTERNS = [
    re.compile(r"^\s*ls\b"),
    re.compile(r"^\s*dir\b"),
    re.compile(r"^\s*cat\s+"),
    re.compile(r"^\s*head\s+"),
    re.compile(r"^\s*tail\s+"),
    re.compile(r"^\s*grep\b"),
    re.compile(r"^\s*rg\b"),
    re.compile(r"^\s*find\s+\S+\s+-name\b"),
    # sed/awk WITHOUT -i (in-place) flag are pure stream readers
    re.compile(r"^\s*sed\s+(?!.*-i\b).*$"),
    re.compile(r"^\s*awk\s+(?!.*-i\s+inplace\b).*$"),
    re.compile(r"^\s*git\s+(status|diff|log|show|reflog|rev-parse|describe|fsck|count-objects|for-each-ref|cat-file)\b"),
    re.compile(r"^\s*git\s+branch\s*(-l|-r|-a|--list|$)"),
    re.compile(r"^\s*git\s+remote\s+(-v|show|$)"),
    re.compile(r"^\s*git\s+config\s+--get\b"),
    re.compile(r"^\s*python\s+-m\s+(pytest|unittest|coverage)\b"),
    re.compile(r"^\s*pytest\b"),
    re.compile(r"^\s*echo\s+[^>|]*$"),  # echo without redirect or pipe-to-writer
    re.compile(r"^\s*pwd\b"),
    re.compile(r"^\s*which\b"),
    re.compile(r"^\s*type\b"),
    re.compile(r"^\s*wc\s+"),
    # gh read-only subcommands
    re.compile(r"^\s*gh\s+(api|auth\s+status|repo\s+view|run\s+(list|view|watch)|issue\s+(view|list)|pr\s+(view|list))\b"),
]


def is_read_only_bash(command: str) -> bool:
    # A file-write redirect (> or >>) means the command writes to disk even
    # when it starts with a read-only verb (e.g. `cat foo > /outside/path`,
    # `grep x f > FILE`). Such a command must NOT be fast-exited as
    # read-only, or its redirect target -- including critical paths -- would
    # escape both the path-extraction and critical-path checks downstream.
    # fd-duplication redirects (2>&1, >&2) are not file writes: the char
    # right after `>` is `&`, which the negated class below excludes, so
    # they do not trip this guard.
    if re.search(r">>?\s*[^\s&|;<>]", command):
        return False
    for pattern in READ_ONLY_BASH_PATTERNS:
        if pattern.match(command):
            return True
    return False


_GIT_BASH_DRIVE_RE = re.compile(r"^/([a-zA-Z])(/|$)")


def _translate_git_bash_path(p: str) -> str:
    """Translate Git Bash `/c/Users/...` form to Windows `C:/Users/...`.

    Git Bash on Windows exposes drive letters as `/<letter>/...`, but
    Python's Path.resolve() on Windows treats `/c/...` as a relative-to-
    current-drive path and produces `C:\\c\\Users\\...` -- broken.
    Translate at the boundary so downstream resolve() works.
    """
    m = _GIT_BASH_DRIVE_RE.match(p)
    if m:
        drive = m.group(1).upper()
        rest = p[m.end():]
        return f"{drive}:/{rest}"
    return p


def normalize_path_for_match(p: str | Path) -> str:
    """Resolve to absolute and use forward slashes for substring match."""
    raw = str(p)
    expanded = os.path.expanduser(raw)
    expanded = _translate_git_bash_path(expanded)
    try:
        resolved = Path(expanded).resolve()
    except (OSError, RuntimeError):
        # Fall back to expanded but unresolved
        resolved = Path(expanded)
    return str(resolved).replace("\\", "/")


def hits_critical_path(target: str | Path) -> str | None:
    """Return matched critical pattern (substring) or None."""
    norm = normalize_path_for_match(target)
    for pat in CRITICAL_PATH_PATTERNS:
        if pat in norm:
            return pat
    return None


def extract_bash_paths(command: str) -> list[tuple[str, str]]:
    """Return [(path, label)] candidates from a Bash command string."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for regex, idx, label in BASH_PATH_PATTERNS:
        for m in regex.finditer(command):
            try:
                p = m.group(idx)
            except IndexError:
                continue
            if not p or p in seen:
                continue
            # Skip obvious non-paths: bare flags, pipes, glob fragments
            if p.startswith("-") or p in {"|", "&&", "||"}:
                continue
            # Strip surrounding quotes if any leaked through
            p = p.strip("'\"")
            if not p:
                continue
            seen.add(p)
            found.append((p, label))
    return found


def is_override_active() -> bool:
    return os.environ.get("CLAUDE_BOUNDARY_OVERRIDE", "").strip() == "1"


def audit_override(command: str, boundary: Boundary, target: str) -> None:
    """Append override-usage record to user-global cache for review."""
    cache_dir = Path.home() / ".claude" / "cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return
    record = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "boundary_path": str(boundary.path),
        "boundary_rule": boundary.rule,
        "target": target,
        "command_preview": command[:200],
        "cwd": os.getcwd(),
    }
    try:
        with open(cache_dir / "boundary_override_audit.jsonl",
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def block(reason: str, target: str, boundary: Boundary, *, critical: bool) -> "NoReturn":  # type: ignore  # noqa: F821
    label = "CRITICAL" if critical else "BOUNDARY"
    sys.stderr.write(
        f"[SESSION {label} GUARD] BLOCKED: target outside session boundary.\n"
        f"  Boundary:        {boundary.path}\n"
        f"  Discovery rule:  {boundary.rule}\n"
        f"  Target:          {target}\n"
        f"  Reason:          {reason}\n"
    )
    if critical:
        sys.stderr.write(
            "  Note: critical paths (~/.ssh, AppData system dirs, "
            "~/.claude/settings.json, etc.) are ALWAYS denied --\n"
            "  CLAUDE_BOUNDARY_OVERRIDE=1 does NOT lift this layer.\n"
        )
    else:
        sys.stderr.write(
            "  Cross-boundary writes are denied by default. To work\n"
            "  on this path, open a NEW Claude Code session with cwd\n"
            "  inside that path's project. The new session will\n"
            "  compute its own boundary.\n"
            "\n"
            "  One-shot override (rare; user-initiated only):\n"
            "    Set CLAUDE_BOUNDARY_OVERRIDE=1 in the parent shell\n"
            "    BEFORE launching Claude Code. Override is session-\n"
            "    scoped; the env var must be inherited from the\n"
            "    launching shell. Override usage is audited at\n"
            "    ~/.claude/cache/boundary_override_audit.jsonl.\n"
        )
    sys.exit(2)


def is_in_user_claude_dir(target: str | Path) -> bool:
    """True if target is under ~/.claude/ (Claude's own user-data dir).

    Memory store, cache, hook scripts -- legitimate writes that the
    Memory tool / hooks themselves perform. Allowed regardless of
    project boundary, EXCEPT for paths matching CRITICAL_PATH_PATTERNS
    (e.g. ~/.claude/settings.json -- still blocked). The exemption is
    checked AFTER critical-paths so self-modify of hook config remains
    denied.
    """
    norm = normalize_path_for_match(target)
    home_norm = str(Path.home().resolve()).replace("\\", "/")
    return norm.startswith(home_norm + "/.claude/")


def check_target(
    target: str,
    boundary: Boundary,
    *,
    command_for_audit: str,
    label: str,
) -> None:
    """Check a single target path; block if disallowed."""
    # Always check critical paths first (override does not bypass these,
    # nor does the ~/.claude/ exemption below)
    crit = hits_critical_path(target)
    if crit:
        block(
            f"matches critical pattern '{crit}'",
            target=target, boundary=boundary, critical=True,
        )

    # ~/.claude/ exemption: Memory store + cache + hook scripts are
    # legitimate writes by the Memory tool / by hooks themselves. Allow
    # even when outside the project boundary, because there is no
    # project boundary that includes ~/.claude/ -- it is the Claude
    # harness's own user-data root, and forbidding writes here would
    # break auto-memory and hook self-update entirely.
    if is_in_user_claude_dir(target):
        return

    # Boundary check
    inside = is_inside_boundary(target, boundary.path)
    if inside:
        return

    # Outside boundary -- last chance: override
    if is_override_active():
        audit_override(command_for_audit, boundary, target)
        return

    block(
        f"path outside boundary tree ({label})",
        target=target, boundary=boundary, critical=False,
    )


def check_repo_health_alarm() -> None:
    """Phase C of proposal harden_indirect_attack_paths.md.

    If repo-health.py wrote an alarm file (damage detected post-Bash),
    block all subsequent Bash/Edit/Write until user manually clears it.
    Converts repo-health from pure audit to audit + brake.

    Alarm path: ~/.claude/cache/repo_health_alarm.json
    Clear: rm ~/.claude/cache/repo_health_alarm.json (PowerShell terminal)
    """
    alarm_path = Path.home() / ".claude" / "cache" / "repo_health_alarm.json"
    if not alarm_path.exists():
        return
    try:
        record = json.loads(alarm_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt alarm file -- block as if alarm is set; user can
        # remove it manually.
        record = {"signals": ["(alarm file unreadable; remove manually to clear)"]}
    sys.stderr.write(
        f"[SESSION BOUNDARY GUARD] BLOCKED: repo-health alarm active\n"
        f"  Alarm file: {alarm_path}\n"
        f"  Triggered:  {record.get('iso', '?')}\n"
        f"  Repo:       {record.get('repo_root', '?')}\n"
        f"  Command:    {record.get('command_preview', '?')[:120]}\n"
        f"  Signals:\n"
    )
    for s in record.get("signals", []):
        sys.stderr.write(f"    - {s}\n")
    sys.stderr.write(
        "\n  All Bash/Edit/Write are blocked until alarm is cleared.\n"
        "  Inspect repo damage, then run from PowerShell terminal:\n"
        f"    Remove-Item '{alarm_path}'\n"
        "  (or in CC: 'rm ~/.claude/cache/repo_health_alarm.json' --\n"
        "  the alarm file path is exempt from boundary check by the\n"
        "  ~/.claude/ exemption, so the rm passes once you confirm.)\n"
    )
    sys.exit(2)


def main() -> None:
    try:
        # Read raw bytes + explicit UTF-8 so a CJK payload is not mis-decoded by
        # a GBK/cp936 locale. Text-mode json.load(sys.stdin) reads in the ambient
        # locale and silently corrupts CJK file paths, making the guard evaluate a
        # garbled path (T-0015; #123). Every sibling hook already does this.
        hook_input = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        # Fail CLOSED. Under global bypassPermissions this guard is the primary
        # backstop; a payload it cannot parse must NOT silently allow a
        # cross-boundary write -- it blocks (unlike the fail-open sibling guards,
        # whose availability posture is deliberate). (#123)
        sys.stderr.write(
            "[SESSION BOUNDARY GUARD] BLOCKED: could not parse tool payload "
            "(failing closed).\n"
        )
        sys.exit(2)

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in {"Bash", "Edit", "Write"}:
        sys.exit(0)

    # Phase C: repo-health alarm gate. Block all Bash/Edit/Write while
    # an alarm is set (set by repo-health.py PostToolUse on damage signals).
    check_repo_health_alarm()

    cwd = os.getcwd()
    try:
        boundary = derive_boundary(cwd)
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[SESSION BOUNDARY GUARD] derive_boundary failed: {exc}; "
            f"falling back to cwd as boundary\n"
        )
        boundary = Boundary(path=Path(cwd).resolve(), rule="cwd", source=None)

    tool_input = hook_input.get("tool_input", {})

    if tool_name in {"Edit", "Write"}:
        target = tool_input.get("file_path", "")
        if not target:
            sys.exit(0)
        check_target(
            target,
            boundary,
            command_for_audit=f"{tool_name}: {target}",
            label=f"{tool_name} file_path",
        )
        sys.exit(0)

    # Bash
    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)
    # Read-only commands: skip path extraction entirely. Avoids the
    # cross-clone `ls` false-positive class.
    if is_read_only_bash(command):
        sys.exit(0)
    paths = extract_bash_paths(command)
    for p, label in paths:
        # Skip empty / non-path tokens
        if not p:
            continue
        check_target(
            p,
            boundary,
            command_for_audit=command,
            label=label,
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
