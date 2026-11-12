---
theme: universal
name: slash-command-hot-reload
description: Claude Code does NOT hot-reload slash-command definitions — .claude/commands/*.md is cached when the session opens and subsequent edits are invisible to that session. After editing a command file, or after a /sync-repos merge or governance-core upgrade that changes command files, the receiving session must EXIT and re-open (or re-invoke the command) for the new definition to take effect. Hooks and skills do not share this constraint.
type: guide
tags: [claude-code, governance, harness, cache, slash-commands, gotcha]
created: 2026-04-17
updated: 2026-11-12
---

# slash-command-hot-reload

## When to apply

- After editing any `.claude/commands/*.md` in your own repo
- After a `/sync-repos` merge or a `governance-core upgrade` that changed
  command files in a clone (check the merge's file list or upgrade's
  overwrite list)
- Diagnosing "I changed `/wrap-up` but it still runs the old version"
- Shipping a breaking update to a slash command's contract (new checklist item, reordered steps, new required arg)

## The rule

| Harness surface | Reload behavior |
|-----------------|-----------------|
| `.claude/commands/*.md` | **Cached at session start. Does NOT hot-reload.** |
| `.claude/hooks/*.py` | Executed fresh on every invocation — edits effective immediately |
| `.claude/skills/*.md` (guides, learned) | Registry re-scans on demand — new files discoverable without restart |
| `skills/` Python modules | Imported lazily — reloadable via usual Python mechanics, unaffected by session lifecycle |

So the single thing that requires a session restart is a changed slash-command `.md` file.

## Consequence

Core can update every clone's command files (through `/sync-repos` and a per-clone upgrade), but every **running** receiver session keeps executing the old cached version until it exits and re-opens. Two observed failure modes:

- `/wrap-up` with 3 items: the 7-item template was on disk, but the in-session cache still held the 3-item version.
- An agent followed a copy of `/wrap-up` loaded early in a long session, from before a step was added, instead of re-invoking the command each phase.

## Recommended flow

After a merge or upgrade that changed command files:

1. List which clones had command files change (the merge diff, or upgrade's overwrite list).
2. Notify each affected agent:
   - Save any in-progress work / finish the current turn.
   - Exit Claude Code and re-open it, or at least re-invoke the command (`/wrap-up` etc.) instead of following a copy from earlier in the conversation.
3. Verify with the first invocation: does `/wrap-up` show the new checklist items? If yes, cache is refreshed.

## Diagnosing a stale cache

Symptom: invoked a command, received the old behavior.

Check:
```bash
# Does the on-disk version already have the new behavior?
grep -c "^- \[" .claude/commands/wrap-up.md    # expect the latest item count
# Compared against what the running session actually executed?
# If they differ → your session is using a pre-update cache → restart.
```

## Why not auto-reload?

Slash-command definitions set the contract for `/name` inside the current session. Hot-reloading would change behavior mid-workflow and surprise the user — e.g., a long `/wrap-up` could start executing new steps partway through. The trade-off favors predictability; you get one deterministic definition per session.

## Related

- `/sync-repos` and `governance-core upgrade` — how command files reach clones (P-0137)
- `.claude/skills/shared-code-per-agent-state.md` — sibling pattern: per-clone copies vs shared state
- `.claude/skills/lesson-classification.md` — this qualifies as a guide (cross-agent harness mechanic, recurring trigger pattern), not a memory hook
