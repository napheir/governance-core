# -*- coding: utf-8 -*-
"""
Claude Code hook: skill-read-tracker.py

Records skill *body loads* that happen via the Read tool, so the skill-usage
funnel's `load` axis is no longer pinned at 0 for learned/guide skills
(P-0113 WS-D, issue #122).

Learned + guide skills are consulted by reading their `.md` body (Read tool),
never through the Skill tool -- so `skill-usage-tracker.py` (PostToolUse Skill)
never sees them and their `use_count` stays 0. This sibling hook listens on
PostToolUse Read: when the file read is a skill `.md` under `.claude/skills/`,
it derives the skill name from the basename and calls
`SkillTracker.record_loaded(name)` (per-day deduped, distinct from record_use).

v1 counts every such Read, including curation reads (extract-skill validation,
tier audits) -- no intent classification. Per-day dedup + the funnel's
proxy-not-causal contract absorb the residual noise (see the P-0115 proposal).

Records land in the invoking agent's per-agent state
(.claude/skills/learned/.usage.json) via governance_core.discovery
.resolve_project_root(), so state follows the invoker, not the hook's location.

Non-blocking; always exits 0. Silent on failure -- tracking is opportunistic,
never critical path (fail-open per runtime-import-discipline).
"""
import json
import os
import sys

_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_ROOT = os.path.normpath(os.path.join(_HOOK_DIR, "..", ".."))

# Basenames under .claude/skills/ that are not real skills.
_NON_SKILL_STEMS = {"README", "_template"}


def _skill_name_from_path(file_path: str) -> str:
    """Return the skill name for a Read of a `.claude/skills/**/*.md`, else "".

    Matches both guides (`.claude/skills/<name>.md`) and learned skills
    (`.claude/skills/learned/<name>.md`); the skill name is the basename stem.
    Returns "" for any path that is not a skill markdown file.
    """
    if not file_path:
        return ""
    norm = file_path.replace("\\", "/")
    if "/.claude/skills/" not in norm and not norm.startswith(".claude/skills/"):
        return ""
    if not norm.endswith(".md"):
        return ""
    stem = os.path.basename(norm)[:-len(".md")]
    if stem in _NON_SKILL_STEMS:
        return ""
    return stem


def _record(name: str) -> None:
    """Push a body-load into the tracker; silent on any error (fail-open)."""
    if not name:
        return
    sys.path.insert(0, _CORE_ROOT)
    try:
        from governance_core.discovery.tracker import SkillTracker
        SkillTracker().record_loaded(name)
    except Exception:
        # Tracking must never break the user's workflow.
        pass


def main() -> None:
    try:
        data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, ValueError, EOFError):
        sys.exit(0)

    # Only PostToolUse Read events; ignore all else.
    if data.get("tool_name") != "Read":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    file_path = tool_input.get("file_path", "") or ""
    _record(_skill_name_from_path(file_path))
    sys.exit(0)


if __name__ == "__main__":
    main()
