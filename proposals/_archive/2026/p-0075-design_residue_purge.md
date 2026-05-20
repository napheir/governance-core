---
id: P-0075
agent: core
status: implemented
created: 2026-05-20
approved_at: 2026-05-20
started_at: 2026-05-20
implemented_in: b4f2d65
implemented_at: 2026-05-20
owner: core
---

# Proposal P-0075: Purge dashboard/HK-trading design residue from package source

## Trigger

User audit (2026-05-20) flagged that `knowledge/design/component-catalog.md`
and `design-principles.md` (rendered by `governance-core install` from package
source `governance_core/knowledge_governance/design/`) still embed
business-specific content from the multi-agent predecessor of this repo:

- `component-catalog.md` lists "Design Assets" at paths that do not exist in
  governance-core (`analysis/dashboard/design/dashboard.pen`,
  `analysis/dashboard/frontend/...`, `research/references/claude-code-source/...`)
- `design-principles.md` mandates the **HK Color Convention** (red = up /
  profit, green = down / loss, CALL/PUT option color families) -- a HK-stock
  trading-specific convention, not a public/universal design principle
- `design-principles.md` references "Design Token Categories" in `lib/theme.ts`
  / `lib/typography.ts` / `lib/spacing.ts` / `lib/format.ts` -- none of which
  exist in governance-core

Same residue extends to `governance_core/agents/design-system-owner.md`
("Dashboard Design System Owner"), which assumes Pencil MCP tools, HK colors,
and the `analysis/dashboard/` layout.

**Why proposal governance applies**: changes package source (Art. 11) +
affects every consumer's autonomy layer (P-0070 prune semantics) + crosses
multiple package subdirs + needs dogfood reinstall + regression validation.

**Consumer-protection sub-trigger**: at least one downstream consumer
(`trade-agent`) installed governance-core 0.5.0/0.6.0 when these files were
still shipping. From that consumer's perspective the three paths are
**install-managed** (recorded in its `.governance/installed_files.json`),
so naive 0.7.0 `_prune_stale` would unlink them -- including business-layer
content the consumer has been editing or referencing as their own design
authority. P-0070 `_capture_drift` would back up the edited form as a drift
envelope in the outbox, but the working file would still disappear. This
proposal must therefore **release** these three paths to business ownership,
not just stop shipping them. See Scope §3 prune-exempt mechanism.

## Scope

Remove design-residue carriers from the package source:

1. **Delete** `governance_core/knowledge_governance/design/` (2 files:
   `component-catalog.md`, `design-principles.md`).
2. **Delete** `governance_core/agents/design-system-owner.md`. Leaves only
   `core-auditor.md` (the governance-audit agent) under `governance_core/agents/`.
3. **Update** `governance_core/installer.py`:
   - Remove the `("knowledge_governance/design", "knowledge/design")` entry
     from `KNOWLEDGE_COPY_MAP` (line 94).
   - Update the inline comment at line ~834 that mentions
     "methodology/design/operations" -- drop the `design` reference.
   - **Add `STALE_PRUNE_EXEMPT` set** (consumer-protection mechanism) with
     the three released paths:
     ```python
     # P-0075: paths released from install-management to business ownership
     # at the 0.6.0 -> 0.7.0 boundary. _prune_stale skips them so a consumer
     # that received the residual design / agent files in 0.5.0/0.6.0 keeps
     # them as business carve-out after upgrading. After release, these
     # paths drop out of installed_files.json naturally (the 0.7.0 install
     # set has no source for them), so the exemption is one-shot: it triggers
     # only on the upgrade that crosses the 0.7.0 line.
     STALE_PRUNE_EXEMPT = {
         "knowledge/design/component-catalog.md",
         "knowledge/design/design-principles.md",
         ".claude/agents/design-system-owner.md",
     }
     ```
     `_prune_stale` adds a single guard line: paths in `STALE_PRUNE_EXEMPT`
     are skipped (logged at INFO as "released to business ownership", not
     pruned). All other prune behavior (capture-drift, manifest-diff
     baseline) unchanged.
4. **Update** `governance_core/knowledge_governance/knowledge-carrier-classes.md`
   §3 sub-directory ownership table: remove the row for `knowledge/design/`.
5. **Update** `governance_core/tools/test_upgrade_dry_run.py`: drop the test
   case at lines 58-60 that asserts `_pkg_source_path("knowledge/design/foo.md")`
   maps to `knowledge_governance/design/foo.md`.

Version bump: `governance_core/__init__.py` + `pyproject.toml` 0.6.0 -> 0.7.0
(minor: removes content from the public install surface; consumers will see
files prune on next `upgrade`).

## Non-Goals

- **Not** writing a replacement "universal design principles" document.
  governance-core is a governance-infrastructure package without UI; there is
  no universal design framework to offer. Consumers who genuinely need a
  Design System Owner agent or design references should author them locally
  (autonomy carve-out, like `.claude/skills/learned/`).
- **Not** changing the carrier-class taxonomy itself; the `reference` class
  stays valid -- only the `knowledge/design/` row in the §3 table is removed.
- **Not** touching consumer-side `knowledge/design/` or
  `.claude/agents/design-system-owner.md` directly. P-0070 prune handles
  removal at the consumer's next `governance-core upgrade`.

## Guardrails

- `edit-write-guard` -- not triggered: no `CLAUDE.md` / `constitution/*.md`
  changes (this proposal does not edit the constitution).
- `command-guard` -- standard scope: deletions via `git rm`, edits via Edit
  tool. Dogfood `governance-core upgrade --project-root .` after package
  source changes.
- `scope-guard` / `boundary-guard` -- all changes within the
  `C:\Users\naphe\workshop-claude\governance-core` boundary.
- `constitutional-review` -- not triggered: no new `.get(k, default)` usage,
  no hardcoded constants introduced.
- `sensitive-data-guard` -- not triggered: no secrets touched.

## Phases

### Phase 1: package-source purge + consumer-protection prune-exempt

- Deliverables:
  - `git rm` `governance_core/knowledge_governance/design/component-catalog.md`
    `governance_core/knowledge_governance/design/design-principles.md`
    `governance_core/agents/design-system-owner.md` (and the empty `design/`
    directory if git leaves it).
  - Edit `governance_core/installer.py`:
    - Remove the `design` entry from `KNOWLEDGE_COPY_MAP`.
    - Tighten the line ~834 comment (drop `design` reference).
    - **Add `STALE_PRUNE_EXEMPT` set + guard line in `_prune_stale`**
      (consumer-protection; see Scope §3).
  - Edit `governance_core/knowledge_governance/knowledge-carrier-classes.md`:
    delete the `knowledge/design/` row in §3 table.
  - Edit `governance_core/tools/test_upgrade_dry_run.py`: remove the
    `knowledge/design/foo.md` mapping case.
  - Extend `governance_core/tools/test_upgrade_dry_run.py` (or a new test
    file) with **prune-exempt regression cases**: build a fake project with
    an old manifest listing all three released paths and the three physical
    files present; run `install()` after the source-removal patches; assert
    that (a) `_prune_stale` returned no entries for the three exempt paths,
    (b) the three files still exist on disk, (c) the new manifest does NOT
    list them.
  - Bump version 0.6.0 -> 0.7.0 in `governance_core/__init__.py` and
    `pyproject.toml`.
- Validation:
  - `python governance_core/tools/test_upgrade_dry_run.py` -- all green, with
    +N prune-exempt cases (one per released path + one boundary case: an
    install-managed but non-exempt stale path is still pruned).
  - `python -m build --wheel` -- builds 0.7.0; inspect wheel: no
    `knowledge_governance/design/`, no `agents/design-system-owner.md`.
  - **Two-leg dogfood**:
    1. `governance-core upgrade --project-root .` on the governance-core
       repo itself. Self-hosted manifest currently lists the three paths
       (we installed our own 0.6.0). Verify: three files stay on disk,
       new manifest does not list them, `doctor` exit 0, hooks 19/registered
       18.
    2. (Optional / consumer-side parity) on a trade-agent or auto-tax-filing
       clone authorized for 0.7.0: same assertions. If unable to run there
       from this session, note the deferral.
  - Full regression: `test_revocation` 24, `test_renewal` 13,
    `test_candidate_attribution` 9, `test_candidate_reminder` 7,
    `test_update_reminder` 9, `test_auth_guard` 9, `test_auth_codec` 11,
    `test_upgrade_dry_run` (post-drop + prune-exempt cases).
- Exit criteria: all tests green; **self-hosted dogfood proves prune-exempt
  preserves the three paths** (governance-core's own copies survive the
  upgrade -- itself the first consumer-protection witness); commit with
  `Implements: P-0075`.

## Approval Criteria

- User confirms the **full purge** scope (matches the AskUserQuestion
  selection 2026-05-20: option A "全部清除").
- User confirms `design-system-owner` agent is acceptable to drop entirely
  from the package source (no covertly-relied-on consumer needs it shipped).
- User confirms version bump to 0.7.0 (vs. 0.6.1 patch) is appropriate for
  a public-surface removal.
- User confirms the **`STALE_PRUNE_EXEMPT` mechanism is the right shape**:
  one-shot consumer-protection at the 0.6.0->0.7.0 boundary; the three
  released paths become business-owned content on the consumer side
  (trade-agent / auto-tax-filing keep their `knowledge/design/*.md` and
  `.claude/agents/design-system-owner.md` files intact, free to maintain
  or delete as they see fit).

## Validation Plan

- Static: `grep -r "design-system-owner\|knowledge/design\|design-principles\|component-catalog\|HK Color" governance_core/` after the purge -- only `installer.py` `STALE_PRUNE_EXEMPT` set matches (intentional); no other hits.
- Wheel inspection: `python -c "import zipfile, glob; z = zipfile.ZipFile(glob.glob('dist/*.whl')[-1]); print('\n'.join(sorted(n for n in z.namelist() if 'design' in n.lower())))"` -- empty (the exempt list lives in `installer.py`, not as a content file).
- **Dogfood** (governance-core self-hosted, was on 0.6.0 -- this **is** the protection-witness consumer):
  post-`governance-core upgrade --project-root .`,
  - `ls knowledge/design/` -- still contains both md files (released to business ownership).
  - `ls .claude/agents/` -- still contains both `core-auditor.md` and `design-system-owner.md`.
  - `python -c "import json; print([f['path'] for f in json.load(open('.governance/installed_files.json'))['files'] if 'design' in f['path'].lower()])"` -- empty (the three paths are no longer install-managed).
  - `governance-core doctor` exit 0; hooks 19/registered 18 (no hook change).
- Regression test counts unchanged for unrelated suites.

## Rollback / Recovery

- All changes in one commit (Phase 1 single-commit pattern, consistent with
  P-0073 / P-0074 follow-ups). Rollback = `git revert <commit>` + `governance-core upgrade`.
- **Primary safety net: `STALE_PRUNE_EXEMPT`** — even if everything else
  about the purge is wrong, consumers do not lose their `knowledge/design/*`
  / `design-system-owner.md` files; they remain physically present, just
  released to business ownership.
- Secondary safety net: P-0070 `_capture_drift` is still in effect for any
  *other* install-managed file the consumer has edited (unrelated to design).
- Version is already released 0.6.0 on PyPI; 0.7.0 release uses the
  same trusted-publisher path. If the release surfaces an issue, yank 0.7.0
  on PyPI and restore the files via `git revert`. Even after yank, consumers
  who upgraded keep their three released paths intact (the exempt did its
  job).

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Consumer (trade-agent, auto-tax-filing) loses `knowledge/design/*.md` or `design-system-owner.md` they treat as business content at upgrade | **Was Med → Now Low** | High if it fired | **`STALE_PRUNE_EXEMPT` set in `_prune_stale`** (one-shot release at 0.6.0->0.7.0 boundary); regression test asserts the three paths survive a simulated upgrade |
| `STALE_PRUNE_EXEMPT` becomes permanent dead weight in `installer.py` (never removed) | Med | Low (3-entry literal set, no behavior beyond first upgrade) | Add a follow-up note in `installer.py` source comment: safe to delete the set in a future major version after all consumers have crossed the 0.7.0 line. The mechanism is self-decaying -- after the first upgrade, the exempt paths drop out of new manifests, so subsequent prunes never look at them |
| `knowledge-carrier-classes.md` §3 still lists `knowledge/design/` after edit | Low | Low | grep audit in Validation Plan covers it |
| `installer.py` comment refers to deleted path | Low | Low | inline comment update in Phase 1 deliverables |
| Version bump confusion (consumers expect new feature for minor bump) | Low | Low | Release notes explicit: "package-source cleanup + consumer-protection prune-exempt; no new user-facing feature" |
| `STALE_PRUNE_EXEMPT` path string typo (paths don't match what's actually in old manifests) | Low | High | The three paths are derived from `KNOWLEDGE_COPY_MAP` `knowledge/design/` + `COPY_CATEGORIES` `.claude/agents/` -- exact match the install-time `dst` resolution; regression test loads a real-shape manifest |

## State Log

- 2026-05-20: draft created by core agent (P-0075)
- 2026-05-20: draft → pending (submit for review: design residue purge)
- 2026-05-20: pending → approved (user signal: 'approved 并开始 Phase 1 实施')
- 2026-05-20: approved → in-progress (Phase 1 start)
- 2026-05-20: in-progress → implemented
