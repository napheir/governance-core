---
id: P-0091
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: 169b7c7
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0091: Release consumer knowledge-rendering tools to business ownership (gc #24)

## Trigger

Issue #24 (from trade-agent, user chose "full release"): gc was extracted from
trade-agent and the extraction swept the consumer's knowledge-**rendering**
tools into the governance package. gc now controls HOW a consumer renders its
knowledge base — a governance→project influence chain that should not exist
(it caused a real dashboard-rollback regression on trade-agent). The boundary:
gc owns governance content / contracts / validators / taxonomy; the project
owns its knowledge and how it renders it. Classify = PROPOSAL_REQUIRED
(changes what gc ships + a governance boundary + consumer-facing + multi-file).

## Scope

Release the three rendering assets from gc install-management to business
(consumer) ownership, reusing the P-0075 mechanism, AND decouple the
gc-managed callers so a fresh consumer that never receives the renderer is not
broken.

**1. Remove from the package source (gc stops shipping/managing them):**
- `governance_core/tools/build_knowledge_dashboard.py`
- `governance_core/tools/build_autogen_blocks.py`
- `governance_core/commands/dashboard.md` (the `/dashboard` skill)

**2. Keep existing consumers' copies (P-0075 release mechanism):** add the
three autonomy-layer paths to `installer.STALE_PRUNE_EXEMPT` so `_prune_stale`
SKIPS them on upgrade (a consumer that already has them keeps them as a
business carve-out instead of having them deleted):
- `tools/build_knowledge_dashboard.py`
- `tools/build_autogen_blocks.py`
- `.claude/commands/dashboard.md`

**3. Stop cross-clone distribution:** drop the two tools from
`sync_infra.ALWAYS_COPY_FILES` (gc no longer distributes a renderer).

**4. Decouple the gc-managed callers (so new consumers don't break):**
- `/learn` Step 5 + `/publish-knowledge` 4.8 currently run
  `tools/build_knowledge_dashboard.py` unconditionally. Make the dashboard
  rebuild **optional / project-provided**: "if the project owns a knowledge
  renderer (released to business ownership, #24), run it; else skip — gc's
  governance workflow does not require a dashboard." A fresh consumer without
  the renderer skips cleanly.

**5. De-attribute gc's ownership claim in contracts/governance content:** the
contract `Tools:/Consumers:` lines (`knowledge_index_schema.md`,
`knowledge_frontmatter_schema.md`, `art_03_contracts.md`) and
`knowledge-html-profile.md` name the specific gc-shipped renderer. Re-word to
"the project's knowledge renderer (e.g. `build_knowledge_dashboard.py`)" — gc
owns the **contract/schema/validator/taxonomy**; the renderer is the
consumer's. Light, attribution-only edits (the mechanisms stay).

**6. Version bump + docs:** bump version; update `docs/core-manual.md`
Released-to-business section to list the #24 release.

## Non-Goals

- **Border-case tools** (`build_skill_index.py`, `skill_catalog.py`,
  `infer_carrier_class.py`): #24 marks them lower-priority "decide separately"
  (they apply a governance taxonomy and do NOT cause data rollback). NOT
  released here.
- The catalog **data** `knowledge/skills/_tiers.json` is already project-owned
  (not gc-managed) — no change.
- No change to the validators gc legitimately keeps (`audit_knowledge.py`,
  `audit_html_profile.py`).
- Not rewriting `knowledge-html-profile.md`'s mechanism prose — only the
  ownership-attribution phrasing.
- gc-the-self-hosted-consumer keeps its own renderer (its autonomy copies are
  preserved by STALE_PRUNE_EXEMPT) — gc's own `/dashboard` still works.

## Guardrails

- **edit-write-guard**: no constitution files; the contracts + clause
  `art_03_contracts.md` are package-source governance content (not `total.md`/
  `agent.core.md`/`CLAUDE.md`), editable directly.
- **boundary-guard**: all edits in-boundary.
- **Art.11**: edit the package source only; the autonomy-layer copies are
  regenerated/pruned by `upgrade` — except the released paths, which
  STALE_PRUNE_EXEMPT now preserves.
- **Art.8 / dogfood**: validated by `upgrade` on this repo — confirm gc keeps
  its own three copies (release mechanism) and `doctor` stays green.
- **Art.11.4**: wheel must drop the three files and stay `governance_core*`.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0091), draft → pending → approved.
- Validation: explicit user approval signal.
- Exit criteria: status = approved.

### Phase 1: Release mechanics (source removal + exempt + sync_infra)

- Deliverables: remove the 3 source files; add 3 paths to STALE_PRUNE_EXEMPT
  (with a #24-boundary comment); drop the 2 tools from ALWAYS_COPY_FILES.
- Validation: wheel no longer contains the 3 files; `git rm` clean.
- Exit criteria: package source no longer ships the renderer.

### Phase 2: Decouple callers + de-attribute + version

- Deliverables: /learn + /publish-knowledge dashboard step made optional;
  contract/profile attribution re-worded; version bump; core-manual updated.
- Validation:
  - `governance-core upgrade --project-root .` → the 3 gc autonomy copies are
    PRESERVED (logged "released to business ownership"), not pruned; `doctor`
    exit 0.
  - `pytest tools/` + standalone family green.
  - wheel isolation clean (3 files absent, only `governance_core*`).
  - grep: no gc-managed file *requires* the renderer unconditionally.
- Exit criteria: suite green; commit `Implements: P-0091`; #24 closed; pushed.

## Approval Criteria

- The 3 rendering files are gone from the package source / wheel, but a dogfood
  `upgrade` PRESERVES gc's own autonomy copies (release, not delete).
- A fresh consumer without the renderer can run `/learn` without the dashboard
  step erroring (it skips).
- gc still owns the contracts/validators/taxonomy; only the renderer ownership
  moved.
- Border-case tools + `_tiers.json` untouched.

## Validation Plan

```bash
# Phase 1
git rm governance_core/tools/build_knowledge_dashboard.py \
       governance_core/tools/build_autogen_blocks.py \
       governance_core/commands/dashboard.md
python -m build --wheel
python -m zipfile -l dist/governance_core-<v>-*.whl   # 3 files absent; only governance_core*/
# Phase 2 — dogfood release (gc keeps its copies)
governance-core upgrade --project-root .              # expect "released to business ownership" x3, no prune
ls tools/build_knowledge_dashboard.py tools/build_autogen_blocks.py .claude/commands/dashboard.md  # still present
governance-core doctor                                # exit 0
python -m pytest tools/ -q
```

## Rollback / Recovery

- Single revert restores the 3 files to the source + the sync_infra entries +
  the skill text; STALE_PRUNE_EXEMPT additions are inert if the files return.
- No data migration. The release is additive-to-consumers (they keep what they
  have); reverting re-manages the files (a consumer's business edits would then
  re-drift, but that is the pre-#24 status quo).

## Risks

- **New-consumer `/learn` break** (the headline, mitigated by Phase 2): without
  the decouple, a fresh consumer's dashboard step would call a missing tool.
  Mitigation: Phase 2 makes the step optional/project-provided — verified by a
  grep that no gc-managed file unconditionally requires the renderer.
- **gc loses its own dashboard** (low): gc is a self-hosted consumer; its
  autonomy copies are preserved by STALE_PRUNE_EXEMPT, so `/dashboard` keeps
  working for gc. Verified by the dogfood upgrade + `ls`.
- **Stale contract attribution** (low): a contract still naming the gc renderer
  would re-assert ownership. Mitigation: Phase 2 re-words the attribution lines.
- **STALE_PRUNE_EXEMPT growth** (cosmetic): the set now carries two release
  cohorts (P-0075 0.7.0 + #24); the comment documents both. Self-decays as
  before.

## State Log

- 2026-06-02: draft created by core agent (P-0091)
- 2026-06-02: draft → pending (submit for review: full release of knowledge-rendering tools (gc #24))
- 2026-06-02: pending → approved (user approval signal: 批准)
- 2026-06-02: approved → implemented
