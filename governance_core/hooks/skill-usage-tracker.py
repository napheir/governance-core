# -*- coding: utf-8 -*-
"""
Claude Code hook: skill-usage-tracker.py

Records skill invocations via the PostToolUse Skill event so the
tracker's weighted_scores() produces real data for SessionStart Tier
A/B injection ranking.

Q5 from harness audit 2026-04-28: previously this hook ALSO listened on
UserPromptSubmit (parsed leading /slash from prompt text), which
double-counted every user-typed `/wrap-up` (once at prompt parse, once
when CC harness invoked the Skill tool). Now PostToolUse-only — Skill
tool firing is the canonical authority on "a skill ran". Edge case lost:
typo `/wrapup` that never fires Skill tool is no longer recorded
(acceptable — typos aren't real skill use).

Records land in the invoking agent's per-agent state
(.claude/skills/learned/.usage.json) via SkillTracker.record_use(),
which routes through skills.discovery.resolve_project_root() so state
follows the invoker, not the hook's physical location.

Non-blocking; always exits 0. Silent on failure — tracking is
opportunistic, never critical path.
"""
import json
import os
import sys

_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_CORE_ROOT = os.path.normpath(os.path.join(_HOOK_DIR, "..", ".."))


def _record(name: str) -> None:
    """Push a use into the tracker; silent on any error."""
    if not name:
        return
    sys.path.insert(0, _CORE_ROOT)
    try:
        from skills.discovery.tracker import SkillTracker
        SkillTracker().record_use(name)
    except Exception:
        # Tracking must never break the user's workflow.
        pass


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, EOFError):
        sys.exit(0)

    # Only PostToolUse Skill events; ignore all else.
    if data.get("tool_name") != "Skill":
        sys.exit(0)

    tool_input = data.get("tool_input") or {}
    name = tool_input.get("skill", "") or ""
    _record(name)
    sys.exit(0)


if __name__ == "__main__":
    main()
