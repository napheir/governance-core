---
theme: universal
name: cross-clone-base-promotion
description: When reviewing or implementing a cross-clone proposal that asks core to promote feature-clone content to master, two separate hazards must be addressed together. (1) Git's 3-way merge collapses feature-only additions when master independently edits nearby lines — base-promotion (landing the content in master so the ancestor base contains it) is the only structural fix; manual re-apply will fail again. (2) Distribution is one-way (master → clone by /sync-repos; package → clone by governance-core upgrade), so any clone-side fix on the same/related files that hasn't been promoted (or upstreamed to governance-core) will be reverse-overwritten. Always grep the proposal author's recent commits for companion fixes, not just the headline content.
type: guide
tags: [governance, sync, multi-clone, merge, proposal-review, drift, gotcha]
created: 2026-04-28
updated: 2026-11-12
---

# cross-clone-base-promotion

## When to apply

- Reviewing a `proposals/*.md` filed by another agent that asks core to land
  content into `master`
- Implementing such a proposal as core
- Before `/sync-repos` or a per-clone `governance-core upgrade` after a master
  change that touches files the source agent has independently modified
- Diagnosing repeated "merge from master keeps stripping our changes" reports
- Diagnosing "upgrade clobbered our local fix" reports

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

### Hazard 2: one-way distribution reverse-drift

There is one wiring model (P-0137), and both of its channels are **one-way**:

- `/sync-repos` merges master → clone. A clone-side edit of a tracked project
  file that master also changed is subject to Hazard 1.
- `governance-core upgrade --project-root <clone>` reinstalls gc-managed files
  from the package. A clone-side edit of a gc-managed file (a gc hook, tool,
  command, contract, clause) is captured as a drift candidate and then
  **replaced** by the package version.

So a clone-side fix that has not been promoted to master — or, for a
gc-managed file, upstreamed to governance-core (`/submit-candidate`) — is
reverse-overwritten by the next merge or upgrade.

This means **before promoting a proposal's headline content, you must
inventory the proposal author's recent commits for companion fixes** that
also need to ride along — otherwise the next `/sync-repos` + upgrade will
silently roll back the companion fix on every clone.

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
   Read each commit's diff. For every clone-only edit, decide:
     - **Universal project content drift** (path correction, format
       alignment, constitution-driven update) → promote to master alongside
       the proposal headline
     - **A gc-managed file** → do not promote a hand edit; upstream it to
       governance-core and take it back through `upgrade`
     - **Per-clone localization** (`.claude/settings.local.json`) → leave in
       clone, do NOT promote

3. **Bundle promotion + companion fixes in a single commit** so the
   regression history is one atomic unit and reviewers see the full picture.

4. **Push master + `/sync-repos`** to merge into all clones, then
   `governance-core upgrade --project-root <clone>` in each clone if gc-managed
   files moved.

5. **Check** from core: `python tools/sync_infra.py`. A `copy-drift` WARN on a
   file you thought was promoted means you missed a companion fix — go back
   to step 2. After the merge, the proposal-author clone's stash pop should
   report "Already up to date" on the touched files — that's the structural
   verification that the feature-only-addition treadmill has ended.

## Triage cheatsheet

| Clone-side commit content | Action |
|---|---|
| Adds rules-scope tool to shared subagent definition | Promote to master if subagent's frontmatter `theme=` matches the source agent (no cross-agent pollution at injection); reject otherwise (use independent extras file pattern) |
| Updates a verification string / path / format that's universally correct | Promote to master verbatim |
| Updates a constitution-derived path that drifted post-Art.X-Y | Promote to master verbatim |
| Edits a gc-managed file (hook, gc tool, gc command, clause) | Upstream to governance-core; `upgrade` would overwrite a local copy |
| Localizes something in `.claude/settings.local.json` | Leave in clone — settings.local.json is intentionally per-clone |
| Adds a per-clone Python module under that clone's scope | Already correct; nothing distributes it |

## Common mistakes

- **Promoting the headline only** — the next merge/upgrade then reverse-drifts
  the companion fixes. Use step 2's grep.
- **Refusing the promotion citing cross-agent pollution** without checking
  `theme:` frontmatter — `theme` already decides which clones' sessions inject
  a skill.
- **Promoting per-clone settings** (`.claude/settings.local.json`) — these are
  intentionally clone-local and promoting breaks the clone-localization design.
- **Treating manual re-apply as a fix** — if the regression evidence shows
  the strip happening twice or more on independent master edits, the only
  fix is base-promotion. Re-apply is not durable.

## Related

- `/sync-repos`, `governance-core upgrade`, and `tools/sync_infra.py` (the
  read-only wiring/drift check) — the one wiring model (P-0137)
- `.claude/skills/lesson-classification.md` — why this is a guide
- `.claude/skills/slash-command-hot-reload.md` — sibling guide on a separate
  distribution hazard (cached command definitions in receiver sessions)
- CLAUDE.md 第十二条 — cross-agent collaboration governance
