# -*- coding: utf-8 -*-
"""
Claude Code SessionStart hook: session-context.py

Outputs recent project state on session start to bridge context
between sessions. Reads STATE.md (recent entries) and checks for
pending proposals.

Non-blocking (always exit 0). Output injected into agent context.
"""
import concurrent.futures
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path  # noqa: F401  (already imported below in submodules)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# agent-core is the authoritative source for synced files.
# __file__ resolves inside agent-core (hook is centrally referenced by all clones).
CORE_ROOT = Path(__file__).resolve().parent.parent.parent


def _detect_repo_root():
    """Detect repo root from git."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _detect_role(root):
    """Detect agent role from branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=root,
        )
        branch = result.stdout.strip()
    except Exception:
        return "core", "unknown"

    role_map = {
        "master": "core", "main": "core",
        "feature/rules": "rules", "feature/trade": "trade",
        "feature/data": "data", "feature/research": "research",
    }
    for prefix, role in role_map.items():
        if branch.startswith(prefix) or branch == prefix:
            return role, branch
    return "core", branch


def _read_recent_state(root, max_entries=2):
    """Read recent STATE.md entries (up to max_entries)."""
    state_file = os.path.join(root, "STATE.md")
    if not os.path.isfile(state_file):
        return ""

    try:
        with open(state_file, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""

    # Extract entries (### headers)
    entries = re.split(r"(?=^### )", content, flags=re.MULTILINE)
    entries = [e.strip() for e in entries if e.strip().startswith("### ")]

    if not entries:
        return "  (no recent entries)"

    lines = []
    for entry in entries[:max_entries]:
        # Extract just the header line
        header = entry.split("\n")[0]
        lines.append(f"  {header}")

    return "\n".join(lines)


def _check_git_hygiene(root):
    """Summarize unpushed commits and uncommitted files.

    Called on SessionStart so every agent sees drift before starting
    new work — prevents committed-but-unpushed history from accumulating
    and flags stale working-tree changes that need attention.
    Returns a multi-line string (empty when tree is clean and
    fully pushed) suitable for injecting into the context banner.
    """
    try:
        ahead_res = subprocess.run(
            ["git", "rev-list", "--count", "@{u}..HEAD"],
            capture_output=True, text=True, timeout=5, cwd=root,
        )
        ahead = int(ahead_res.stdout.strip() or "0") if ahead_res.returncode == 0 else 0
    except (subprocess.TimeoutExpired, ValueError, OSError):
        ahead = 0

    try:
        status_res = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, timeout=5, cwd=root,
        )
        status_lines = [l for l in status_res.stdout.splitlines() if l.strip()]
    except (subprocess.TimeoutExpired, OSError):
        status_lines = []

    if ahead == 0 and not status_lines:
        return ""

    lines = ["Git hygiene:"]
    if ahead > 0:
        lines.append(f"  unpushed commits: {ahead} (consider: git push)")
    if status_lines:
        modified = sum(1 for l in status_lines if l[:2].strip().startswith(("M", "A", "D", "R")))
        untracked = sum(1 for l in status_lines if l.startswith("??"))
        parts = []
        if modified:
            parts.append(f"{modified} modified/staged")
        if untracked:
            parts.append(f"{untracked} untracked")
        lines.append(f"  uncommitted: {', '.join(parts)} (review with: git status)")
    lines.append("  Guide: .claude/skills/session-start-git-hygiene.md")
    return "\n".join(lines)


def _check_skill_drift(root):
    """Warn if this clone's generated CLAUDE.md is out of sync with sources.

    Delegates to tools/regen_constitution.py --check. This single check
    covers both constitution/*.md staleness and any synced skill that
    contributes to CLAUDE.md content. Prior hand-rolled text-compare was
    replaced because the generator is now the single source of truth for
    "is this clone's forced context up to date".

    Returns a multi-line warning string (empty when in-sync or no generator).
    """
    regen = CORE_ROOT / "tools" / "regen_constitution.py"
    if not regen.is_file():
        return ""  # generator not deployed yet
    try:
        result = subprocess.run(
            [sys.executable, str(regen), "--check", "--root", str(root)],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return ""

    if result.returncode == 0:
        return ""

    lines = [
        "[CONSTITUTION DRIFT] CLAUDE.md is out of sync with constitution/ sources:",
        f"  {result.stderr.strip() or result.stdout.strip()}",
        f"  Fix: python {regen.as_posix()} --root {Path(root).as_posix()}",
        "  Risk: agent forced-context lags behind source-of-truth.",
    ]
    return "\n".join(lines)


# ---------- Cross-clone drift check (core-only) ----------

# Threshold: warn if any feature clone is BEHIND_THRESHOLD+ commits behind master,
# OR DAYS_THRESHOLD+ days since last sync (merge-base age).
_DRIFT_BEHIND_THRESHOLD = 10
_DRIFT_DAYS_THRESHOLD = 3.0
_DRIFT_CACHE_TTL = 600  # seconds; reuse cache if fresher
_DRIFT_OVERALL_TIMEOUT = 3.0  # hard cap for parallel git calls
_DRIFT_PER_CALL_TIMEOUT = 2  # per-subprocess timeout
_DRIFT_CLONE_NAMES = ("agent-rules", "agent-trade", "agent-data", "agent-research")


def _drift_cache_path() -> Path:
    return Path.home() / ".claude" / "cache" / "drift_check.json"


def _drift_one_clone(clone_root: Path) -> dict:
    """Return drift dict for a single clone (3 git calls max).

    Layout:
      {"name": "agent-rules", "behind": int, "days": float, "branch": str}
      {"name": "agent-rules", "error": "<msg>"}     -- on any subprocess failure
    """
    name = clone_root.name
    if not (clone_root / ".git").exists():
        return {"name": name, "error": "not a clone"}
    try:
        cnt = subprocess.run(
            ["git", "-C", str(clone_root), "rev-list", "--count", "HEAD..origin/master"],
            capture_output=True, text=True, timeout=_DRIFT_PER_CALL_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return {"name": name, "error": "rev-list timeout"}
    if cnt.returncode != 0:
        return {"name": name, "error": "no origin/master"}
    behind = int(cnt.stdout.strip() or "0")

    try:
        br = subprocess.run(
            ["git", "-C", str(clone_root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=_DRIFT_PER_CALL_TIMEOUT,
        )
        branch = br.stdout.strip() if br.returncode == 0 else "?"
    except (subprocess.TimeoutExpired, OSError):
        branch = "?"

    if behind == 0:
        return {"name": name, "behind": 0, "days": 0.0, "branch": branch}

    try:
        mb = subprocess.run(
            ["git", "-C", str(clone_root), "merge-base", "HEAD", "origin/master"],
            capture_output=True, text=True, timeout=_DRIFT_PER_CALL_TIMEOUT,
        )
        mb_sha = mb.stdout.strip()
        ts_res = subprocess.run(
            ["git", "-C", str(clone_root), "log", "-1", "--format=%ct", mb_sha],
            capture_output=True, text=True, timeout=_DRIFT_PER_CALL_TIMEOUT,
        )
        ts = int(ts_res.stdout.strip() or "0")
        days = (time.time() - ts) / 86400.0 if ts else 0.0
    except (subprocess.TimeoutExpired, OSError, ValueError):
        days = 0.0

    return {"name": name, "behind": behind, "days": round(days, 1), "branch": branch}


def _format_drift_warning(results: list) -> str:
    """Format hits exceeding either threshold as a multi-line WARN block."""
    hits = [
        r for r in results
        if "behind" in r and (
            r["behind"] >= _DRIFT_BEHIND_THRESHOLD
            or r["days"] >= _DRIFT_DAYS_THRESHOLD
        )
    ]
    if not hits:
        return ""
    lines = [
        "[DRIFT WARN] Feature clones behind master "
        f"(thresholds: {_DRIFT_BEHIND_THRESHOLD}+ commits or {_DRIFT_DAYS_THRESHOLD:.0f}+ days):"
    ]
    for r in sorted(hits, key=lambda x: -x["behind"]):
        lines.append(
            f"  {r['name']:<16} behind={r['behind']:>3} commits, "
            f"{r['days']:>4.1f} days since last merge ({r['branch']})"
        )
    lines.append("  Fix: /sync-repos (after pushing core's pending commits)")
    return "\n".join(lines)


def _check_cross_clone_drift(role: str) -> str:
    """Cross-clone drift check (core-only, cached, parallel).

    Cost budget: cold ~150ms (4 parallel × 3 git calls × ~50ms each, capped
    at 3s); warm ~5ms (cache file read). Returns "" silently when no
    threshold crossed -- session header stays clean.

    Cache key: {clone -> behind/days/branch}. TTL 600s. On TTL hit OR
    overall-timeout, return cached output (best-effort).
    """
    if role != "core":
        return ""

    cache_file = _drift_cache_path()
    now = time.time()
    cached_output = ""

    if cache_file.is_file():
        try:
            with open(cache_file, encoding="utf-8") as f:
                cached = json.load(f)
            if now - cached.get("ts", 0) < _DRIFT_CACHE_TTL:
                return cached.get("output", "")
            cached_output = cached.get("output", "")  # fallback if recompute fails
        except (OSError, json.JSONDecodeError):
            pass

    # Compute fresh
    parent = CORE_ROOT.parent  # <install-root>/
    clone_paths = [parent / name for name in _DRIFT_CLONE_NAMES]
    clone_paths = [p for p in clone_paths if p.exists()]
    if not clone_paths:
        return cached_output

    results = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(_drift_one_clone, p): p for p in clone_paths}
            done, not_done = concurrent.futures.wait(
                futures, timeout=_DRIFT_OVERALL_TIMEOUT,
                return_when=concurrent.futures.ALL_COMPLETED,
            )
            for fut in done:
                try:
                    results.append(fut.result(timeout=0.1))
                except Exception:
                    pass
            for fut in not_done:
                fut.cancel()
    except Exception:
        return cached_output

    output = _format_drift_warning(results)

    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({"ts": now, "output": output, "results": results}, f)
    except OSError:
        pass

    return output


def _check_restart_required() -> str:
    """Surface sync_infra's pending-restart marker (R9 from harness audit).

    sync_infra.py writes ~/.claude/cache/restart_required.json after
    updating slash-command files in any clone. The next SessionStart in
    any clone displays the warning once, then deletes the marker so it
    doesn't re-surface forever.
    """
    marker = Path.home() / ".claude" / "cache" / "restart_required.json"
    if not marker.is_file():
        return ""
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    clones = data.get("clones", [])
    reason = data.get("reason", "infra change")
    ts = data.get("ts", 0)
    age_min = max(0, (time.time() - ts) / 60.0)

    lines = [
        "[RESTART REQUIRED] sync_infra reported pending changes "
        f"({age_min:.0f} min ago, reason: {reason}):"
    ]
    for c in clones:
        lines.append(f"  - {c}")
    lines.append(
        "  → Exit and re-open Claude Code in each affected clone "
        "for new slash-command definitions to load."
    )

    # Single-shot: delete marker so subsequent sessions don't re-display.
    try:
        marker.unlink()
    except OSError:
        pass

    return "\n".join(lines)


def _emit_skill_injection(root) -> str:
    """Emit lazy skill-counts summary (counts-only, ~3 lines).

    Per proposals/prefix_cost_optimization.md C3 (approved 2026-05-07):
    Replaces full Tier A+B manifest dump (~55 lines / ~6.7KB / ~1650 tokens
    of SessionStart prompt prefix) with a counts-only summary. Skills are
    still discoverable via the Skill tool's lazy listing; the routing
    index handles auto-injection of governance docs.

    Counts are computed via direct file scan (non-recursive glob over
    .claude/skills/*.md for guides + .claude/skills/learned/*.md for
    learned). No subprocess; no TTL cache needed (constant-time op).
    """
    skills_dir = Path(root) / ".claude" / "skills"
    if not skills_dir.is_dir():
        return ""
    try:
        guides = sum(1 for p in skills_dir.glob("*.md") if p.is_file())
        learned = 0
        learned_dir = skills_dir / "learned"
        if learned_dir.is_dir():
            learned = sum(1 for p in learned_dir.glob("*.md") if p.is_file())
    except OSError:
        return ""

    return (
        f"[Skills (L0)] {learned} learned + {guides} guides discovered. "
        "Body lazy via Skill tool.\n"
        "  Full manifest: python -m governance_core.discovery.registry --format table\n"
        "  Routing index: knowledge/INDEX.routing.json "
        "(auto-injected by prompt-context-router on keyword match)"
    )


def _proposal_status(fpath: str) -> str:
    """Parse the `status:` line from frontmatter; default 'pending' if missing.

    Per contracts/proposal_frontmatter_schema.md v1.0.0. Backward-compat:
    files lacking frontmatter are treated as 'pending' so the listing
    doesn't break during transition. Audit (tools/audit_proposals.py)
    reports the missing field separately.
    """
    try:
        with open(fpath, encoding="utf-8") as fh:
            head = fh.read(800)  # 800 chars covers any reasonable frontmatter
    except OSError:
        return "pending"
    m = re.search(r"^status:\s*(\S+)", head, re.MULTILINE)
    return m.group(1) if m else "pending"


def _check_proposals(root, role):
    """Check pending/approved/in-progress proposals across 3 regions (P-0001 Phase 3).

    Scans in priority order:
      1. shared_state/proposals/<role>/  — self bucket (highest priority)
      2. shared_state/proposals/<other>/ — cross-agent buckets (folded
         summary; only count, not full list, to avoid banner bloat)
      3. proposals/*.md (legacy top-level, exclude `_*.md` artifacts and
         `p-NNNN-` already-migrated entries which live in shared_state)

    Filters by frontmatter status: visible = {pending, approved, in-progress}.
    draft, implemented, superseded, rejected are hidden (would pollute
    SessionStart banner; implemented/terminal grow forever).
    """
    visible_statuses = {"pending", "approved", "in-progress"}

    # Region 1+2: shared_state/proposals/<agent>/ (in-flight, all 5 agents)
    shared_state_root = os.path.abspath(
        os.path.join(root, "..", "shared_state", "proposals")
    )
    self_bucket = []
    other_buckets = {}  # agent_name -> count
    if os.path.isdir(shared_state_root):
        for agent_name in sorted(os.listdir(shared_state_root)):
            agent_dir = os.path.join(shared_state_root, agent_name)
            if not os.path.isdir(agent_dir):
                continue
            for f in sorted(os.listdir(agent_dir)):
                if not f.endswith(".md") or f == "README.md":
                    continue
                fpath = os.path.join(agent_dir, f)
                if not os.path.isfile(fpath):
                    continue
                if _proposal_status(fpath) not in visible_statuses:
                    continue
                if agent_name == role:
                    self_bucket.append(f)
                else:
                    other_buckets[agent_name] = other_buckets.get(agent_name, 0) + 1

    # Region 3: legacy proposals/*.md top level (excl. _archive, _*.md, p-NNNN-*)
    legacy_list = []
    legacy_dir = os.path.join(root, "proposals")
    if os.path.isdir(legacy_dir):
        for f in sorted(os.listdir(legacy_dir)):
            if not f.endswith(".md"):
                continue
            if f.startswith("_"):
                continue
            if f.startswith("p-") and len(f) > 7 and f[2:6].isdigit():
                # p-NNNN-* file at legacy root = transitional, already in audit;
                # don't double-list (will move to shared_state via Phase 4)
                pass
            fpath = os.path.join(legacy_dir, f)
            if not os.path.isfile(fpath):
                continue
            if _proposal_status(fpath) not in visible_statuses:
                continue
            # Mentions-this-agent heuristic (preserve v1 behavior)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    head = fh.read(800)
                if role in head.lower() or "all" in head.lower():
                    legacy_list.append(f)
            except OSError:
                pass

    parts = []
    if self_bucket:
        parts.append(
            f"  Pending proposals ({role}, shared_state): "
            + ", ".join(self_bucket)
        )
    if other_buckets:
        summary = ", ".join(f"{a}={n}" for a, n in sorted(other_buckets.items()))
        parts.append(f"  Cross-agent pending: {summary}")
    if legacy_list:
        parts.append("  Legacy pending (proposals/): " + ", ".join(legacy_list))
    return "\n".join(parts)


def main():
    """Output session context on startup."""
    try:
        json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, EOFError):
        pass

    root = _detect_repo_root()
    if not root:
        sys.exit(0)

    role, branch = _detect_role(root)
    state_summary = _read_recent_state(root)
    proposals = _check_proposals(root, role)
    git_hygiene = _check_git_hygiene(root)
    skill_drift = _check_skill_drift(root)
    cross_clone_drift = _check_cross_clone_drift(role)

    output = [
        f"[Session Context] agent={role}, branch={branch}",
        "Recent state:",
        state_summary,
    ]
    if proposals:
        output.append(proposals)
    if git_hygiene:
        output.append(git_hygiene)
    if skill_drift:
        output.append(skill_drift)
    if cross_clone_drift:
        output.append(cross_clone_drift)

    restart_warning = _check_restart_required()
    if restart_warning:
        output.insert(1, restart_warning)  # right after banner

    skill_injection = _emit_skill_injection(root)
    if skill_injection:
        output.append(skill_injection)

    print("\n".join(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
