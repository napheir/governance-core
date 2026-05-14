---
theme: core-only
owner: core
---

# /sync-infra - Cross-agent harness infrastructure sync

Deploy core harness capabilities to all agent clones. Run this after any architectural upgrade in agent-core.

## When to Use

- After adding or modifying shared harness components (hooks, commands, skill infrastructure)
- After upgrading /wrap-up with new steps
- After adding new Notification hooks that all agents should have
- As part of any architecture-level change in agent-core

## Workflow

1. **Dry-run first** to review what will change:
   ```bash
   python tools/sync_infra.py
   ```

2. **Review the output**: Verify all pending [COPY], [MKDIR], [ADD] actions are expected.

3. **Execute**:
   ```bash
   python tools/sync_infra.py --execute
   ```

4. **Verify**: Re-run without --execute to confirm all items show [OK].

5. **Single agent** (if needed):
   ```bash
   python tools/sync_infra.py --execute --agent rules
   ```

## What Gets Synced

| Component | Source (core) | Action |
|-----------|--------------|--------|
| `/wrap-up` command | `.claude/commands/wrap-up.md` | Copy verbatim |
| `/extract-skill` command | `.claude/commands/extract-skill.md` | Copy verbatim |
| `skill-nudge.py` hook | `.claude/hooks/skill-nudge.py` | Copy + register in settings |
| `learned/` directory | `.claude/skills/learned/` | Create if missing |

## What Does NOT Get Synced

- Agent-specific commands (each agent has its own set)
- Agent-specific hooks with clone-specific paths (scope-guard, etc.)
- Sub-constitutions (CLAUDE.md is agent-owned)
- permissions in settings.local.json (agent-specific)

## Properties

- **Idempotent**: safe to run multiple times (skips up-to-date files)
- **Non-destructive**: never deletes files, only copies or appends
- **Path-aware**: hook registrations use each agent's own absolute path

## Notes

- New shared infrastructure components should be added to SYNC_FILES in `tools/sync_infra.py`
- Run this tool from agent-core working directory only (it's a core scope tool)
- Reference: Constitution Art.12 (cross-agent collaboration)
