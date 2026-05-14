---
theme: universal
name: slash-command-hot-reload
description: Claude Code does NOT hot-reload slash-command definitions — .claude/commands/*.md is cached when the session opens and subsequent edits are invisible to that session. After editing a command file or running sync_infra that copies command files, the receiving session must EXIT and re-open for the new definition to take effect. Hooks and skills do not share this constraint.
type: guide
tags: [claude-code, governance, harness, cache, slash-commands, gotcha]
created: 2026-04-17
updated: 2026-04-17
---

# slash-command-hot-reload

## When to apply

- After editing any `.claude/commands/*.md` in your own repo
- After `python tools/sync_infra.py --execute` reports `[COPY]` on command files (it now prints a RESTART REQUIRED section listing affected agents)
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

A sender (typically `core` running `sync_infra`) can update every clone's command files, but every **running** receiver session will keep executing the old cached version until it exits and re-opens. This is exactly the trade wrap-up-with-3-items failure mode: `sync_infra` had delivered the 7-item template, the command file on disk was current, but the in-session cache still held the 3-item version.

## Recommended flow

After `sync_infra.py --execute`:

1. Read the `[RESTART REQUIRED]` section printed by sync_infra — it lists exactly which agents had command updates.
2. Notify each affected agent:
   - Save any in-progress work / finish the current turn.
   - Exit Claude Code.
   - Re-open it; the new command is now active.
3. Optionally commit the synced command files in the receiving repo so the change is under version control:
   ```bash
   git add .claude/commands/wrap-up.md .claude/commands/extract-skill.md
   git commit -m "chore(infra): sync slash-command templates from core"
   ```
4. Verify with the first invocation: does `/wrap-up` show the new checklist items? If yes, cache is refreshed.

## Diagnosing a stale cache

Symptom: invoked a command, received the old behavior.

Check:
```bash
# Does the on-disk version already have the new behavior?
grep -c "^- \[" .claude/commands/wrap-up.md    # expect 7 if latest
# Compared against what the running session actually executed?
# If they differ → your session is using the pre-sync cache → restart.
```

## Why not auto-reload?

Slash-command definitions set the contract for `/name` inside the current session. Hot-reloading would change behavior mid-workflow and surprise the user — e.g., a long `/wrap-up` could start executing new steps partway through. The trade-off favors predictability; you get one deterministic definition per session.

## Related

- `tools/sync_infra.py` — prints `[RESTART REQUIRED]` after copying commands
- `.claude/skills/shared-code-per-agent-state.md` — sibling pattern: hooks centralized (auto-live), commands copied (needs restart)
- `.claude/skills/lesson-classification.md` — this qualifies as a guide (cross-agent harness mechanic, recurring trigger pattern), not a memory hook
