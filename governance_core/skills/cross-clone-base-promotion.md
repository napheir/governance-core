---
theme: universal
name: cross-clone-base-promotion
description: When reviewing or implementing a cross-clone proposal that asks core to promote feature-clone content to master, two separate hazards must be addressed together. (1) Git's 3-way merge collapses feature-only additions when master independently edits nearby lines — base-promotion (landing the content in master so the ancestor base contains it) is the only structural fix; manual re-apply will fail again. (2) sync_infra is one-way (master → clone), so any clone-side fix on the same/related files that hasn't been promoted will be reverse-overwritten on the next sync. Always grep the proposal author's recent commits for companion fixes, not just the headline content.
type: guide
tags: [governance, sync, multi-clone, merge, proposal-review, drift, gotcha]
created: 2026-04-28
updated: 2026-04-28
---

# cross-clone-base-promotion

## When to apply

- Reviewing a `proposals/*.md` filed by another agent that asks core to land
  content into `master`
- Implementing such a proposal as core
- Before running `tools/sync_infra.py --execute` after a master change that
  touches files the source agent has independently modified
- Diagnosing repeated "merge from master keeps stripping our changes" reports
- Diagnosing "sync_infra clobbered our local fix" reports

## The two hazards

### Hazard 1: 3-way merge collapses feature-only additions

Git's `ort` (and `recursive`) 3-way merge sees three states for a touched
region:

| Side | State |
|------|-------|
| ancestor base | original content |
| master (theirs) | edited the region for an unrelated reason |
| feature (ours) | added new lines in the same region |

When master edits lines adjacent to the feature-only addition, the merge
strategy treats the master-side edit as the conflict-free continuation of
the unchanged base, and the feature-only addition is dropped. No conflict
markers; the additions just disappear from the merge result.

The pattern repeats every time master touches that region. Manual re-apply
on the feature side is a treadmill — the next master edit on adjacent
lines will strip them again.

**The only structural fix is base-promotion**: land the addition in master
so the ancestor base on every future merge already contains it. Once base
contains the lines, the merge geometry no longer asks git to choose between
"present in feature, absent in base, master modified nearby" and the lines
survive.

### Hazard 2: sync_infra reverse-drift

`tools/sync_infra.py` is **one-way**: master → clone. It does NOT pull
clone-local edits back into master. Any clone-side fix to a sync_infra-
routed file that hasn't been promoted will be **reverse-overwritten** the
next time sync_infra runs against that file.

Symptom in dry-run: `[COPY] foo.md -- would copy` for a file the clone
already has the "right" version of (or where the clone is ahead of master).

This means **before promoting a proposal's headline content, you must
inventory the proposal author's recent commits for companion fixes** that
also need to ride along — otherwise running sync_infra after the
promotion will silently roll back the companion fix on every clone.

## Combined workflow (proposal review → implementation)

1. **Read the proposal headline content** and confirm the diagnosis. If the
   reported symptom is "master merge keeps stripping our X," Hazard 1 is at
   play and base-promotion is required.

2. **Grep the proposal author's recent commits** (look at the linked
   regression evidence commits + anything else they touched in the same
   files):
   ```bash
   git -C ../agent-<author> log --stat --since="<window>" -- <touched_paths>
   ```
   Read each commit's diff. For every clone-only edit on a sync_infra-routed
   file (`.claude/commands/`, `.claude/agents/`, `.claude/skills/`,
   `.claude/hooks/edit-write-guard.py` and `scope-guard.py`, `tools/`,
   `contracts/`, `skills/`, plus `ALWAYS_COPY_FILES`), decide:
     - **Universal content drift** (path correction, format alignment,
       constitution-driven update) → promote to master alongside the
       proposal headline
     - **Per-clone localization** (`.claude/settings.local.json` paths,
       per-clone hook removals like centralized-hook deletions) → leave in
       clone, do NOT promote

3. **Bundle promotion + companion fixes in a single commit** so the
   regression history is one atomic unit and reviewers see the full picture.

4. **Run sync_infra dry-run** and verify the pending action list matches
   expectation:
   - Promoted theme=rules content → only routes to that one clone
   - Universal companion fixes → routes to all clones except the proposal
     author (whose version already matches master after promotion)
   - **If a clone other than the author still shows `[COPY]` on a file you
     thought was promoted, you missed a companion fix** — go back to step 2

5. **Execute sync_infra**, then run a second dry-run and confirm 0 pending.

6. **Push master + `/sync-repos`** to merge into all clones. After merge,
   the proposal-author clone's stash pop should report "Already up to date"
   on the touched files — that's the structural verification that the
   feature-only-addition treadmill has ended.

## Triage cheatsheet

| Clone-side commit content | Action |
|---|---|
| Adds rules-scope tool to shared subagent definition | Promote to master if subagent's frontmatter `theme=` matches the source agent (no cross-agent pollution at routing layer); reject otherwise (use independent extras file pattern) |
| Updates a verification string / path / format that's universally correct | Promote to master verbatim |
| Updates a constitution-derived path that drifted post-Art.X-Y | Promote to master verbatim |
| Localizes hook absolute path in `.claude/settings.local.json` | Leave in clone — settings.local.json is intentionally per-clone |
| Deletes a hook that was centralized via core absolute-path reference | Leave in clone — each clone owns its `.claude/hooks/` cleanup |
| Adds a per-clone Python module under that clone's scope | Already correct; not a sync_infra-routed file |

## Common mistakes

- **Promoting the headline only** — sync_infra then reverse-drifts the
  companion fixes the next time it runs. Use step 2's grep.
- **Refusing the promotion citing cross-agent pollution** without checking
  `theme:` frontmatter — sync_infra's theme routing already prevents
  pollution for theme=`<agent>` files.
- **Promoting per-clone settings** (`.claude/settings.local.json` paths,
  centralized-hook removals) — these are intentionally clone-local and
  promoting breaks the clone-localization design.
- **Treating manual re-apply as a fix** — if the regression evidence shows
  the strip happening twice or more on independent master edits, the only
  fix is base-promotion. Re-apply is not durable.

## Related

- `tools/sync_infra.py` — `ALWAYS_COPY_FILES`, `SKILL_DIRS`, theme routing
  logic; the authoritative source for "what gets routed to which clone"
- `.claude/skills/lesson-classification.md` — why this is a guide
- `.claude/skills/slash-command-hot-reload.md` — sibling guide on a separate
  sync_infra hazard (cached command definitions in receiver sessions)
- CLAUDE.md 第十二条 — cross-agent collaboration governance
