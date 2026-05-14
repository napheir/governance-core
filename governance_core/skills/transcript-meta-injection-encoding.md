---
theme: universal
name: transcript-meta-injection-encoding
description: When writing or auditing a Claude Code hook that walks the transcript JSONL backward to find a user-turn boundary or a prior tool_use, type=user entries with isMeta=True or sourceToolUseID are NOT real user-turn boundaries — they are slash-command / Skill body injections that continue the assistant turn. Treat them as non-boundary, otherwise walk-back stops at the injection and the originating Skill tool_use becomes invisible.
type: guide
tags: [claude-code, harness, hooks, transcript, walk-back, slash-commands, skills, gotcha]
created: 2026-04-28
updated: 2026-04-28
---

# transcript-meta-injection-encoding

## When to apply

- Writing or reviewing any Claude Code hook that opens `transcript_path` and walks entries backward looking for the most recent **user-turn boundary** (entry-point gates, "did the user authorize this within the current turn" checks, etc.)
- Diagnosing an entry-point hook that intermittently blocks legitimate calls routed via a slash command or Skill (e.g., rules-agent's `/learn` getting "BLOCKED (entry-point)" on `knowledge/**` writes)
- Designing any walk-back logic that searches for a prior `tool_use` (Skill, Agent, custom registry call) whose authorization should unlock subsequent same-turn writes
- Auditing log payloads where `transcript_path` decisions look inconsistent across calls in what feels like the same logical turn

## The encoding fact

Claude Code transcripts encode **three different things** as `type=user` JSONL entries. Only the first is a real boundary:

| Shape | type | content | isMeta | sourceToolUseID | Real user turn? |
|-------|------|---------|--------|-----------------|-----------------|
| User-typed message | `user` | string OR list of `text` blocks | absent / `False` | absent / empty | **Yes** |
| Tool-result reply | `user` | list containing a `tool_result` block | absent / `False` | absent / empty | No (tool plumbing) |
| **Slash-command / Skill body injection** | `user` | list of `text` blocks (the skill body) | **`True`** | **non-empty `toolu_...`** linking to the Skill tool_use | **No** (continuation of assistant turn) |

The slash-command injection looks superficially identical to a real user message (string-or-text-list, no tool_result block) — both `isMeta` and `sourceToolUseID` are the only stable distinguishers.

### Empirical evidence

On rules-agent transcript `0522a3c5-...jsonl` (representative sample): all 12 user-typed messages had `isMeta=None / sourceToolUseID=None / content=str`; both Skill body injections had `isMeta=True / sourceToolUseID=toolu_... / content=list[1 text block]`. Marker disjoint, no false positives.

## The gotcha

A naive boundary check that only looks at "is type=user AND no tool_result block in content" returns `True` on the injection, so backward walks **break at the injection** and never reach the `Skill` / `Agent` tool_use that originally authorized the in-turn action. The hook then thinks no authorization occurred and blocks downstream writes.

This bit `edit-write-guard.py`'s `_is_real_user_turn_boundary` (commit 2ac9917): rules-agent invoking `/learn` → Skill tool_use → tool_result → **isMeta-tagged skill body** → assistant Edit on `knowledge/**` was blocked because walk-back stopped at the skill body and never saw the Skill tool_use one entry earlier.

## The rule

```python
def _is_real_user_turn_boundary(entry: dict) -> bool:
    if entry.get("type") != "user":
        return False
    # Slash-command / Skill body injections wear user clothes but are
    # assistant-turn continuations. Skip them.
    if entry.get("isMeta") is True or entry.get("sourceToolUseID"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return False
        return True
    return False
```

Either marker (`isMeta` or `sourceToolUseID`) is independently sufficient. Checking both is defensive against future encoding drift where one might be omitted.

## Sibling considerations

- **`isSidechain=True`** marks subagent-internal entries (the parent's transcript shows `isSidechain=False`; the subagent runs in a separate transcript file under `/subagents/`). Different concern from this guide.
- **`<system-reminder>` blocks** appear inside `tool_result` content (and inside real user messages) as injected reminders — they don't change the entry's type and aren't a separate top-level entry kind. Don't conflate with `isMeta`.
- **`type=attachment`, `type=last-prompt`, `type=summary`** are non-user housekeeping entries; skip them in any walk-back loop.

## Related

- `.claude/hooks/edit-write-guard.py` — `_is_real_user_turn_boundary`, the canonical implementation of this rule (Layers 3 + 4)
- `.claude/skills/lesson-classification.md` — why this is a guide (cross-agent harness mechanic) not a memory hook
- `.claude/skills/slash-command-hot-reload.md` — sibling CC-platform fact about command file caching
