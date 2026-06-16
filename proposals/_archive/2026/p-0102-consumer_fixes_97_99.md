---
id: P-0102
agent: core
status: implemented
created: 2026-06-16
approved_at: 2026-06-16
started_at: 2026-06-16
implemented_in: f181a12
implemented_at: 2026-06-16
owner: core
---

# Proposal P-0102: Relocate maintainer-only tests out of consumer file-set (#97) + carrier-aware learn.md update timestamp (#99)

## Trigger

Two consumer-reported (trade-agent, against 0.28.0) governance-hygiene bugs,
bundled into one reviewed proposal per the P-0099 precedent:

- **#97** — the consumer install manifest materializes maintainer-only tests
  into `tools/`. These import maintainer modules (`maintainer/`, not in the
  consumer distribution), so any consumer operation that imports/collects the
  `tools/test_*.py` set fails at import time. Audit of
  `governance_core/tools/test_*.py` for `sys.path.insert(... "maintainer") +
  import <maintainer_module>` finds **two** offenders: `test_curate_gate.py`
  (imports `curate_gate`) and `test_candidate_intake.py` (imports
  `candidate_intake`). (`test_auth_guard.py` / `test_renewal.py` only mention
  "maintainer" in comments / build a `tmp_path/"maintainer"` fixture and
  import only the distributed `governance_core` — consumer-safe, not moved.)
- **#99** — `learn.md` Step 3's update discipline bumps the YAML frontmatter
  `updated:` date, but Step 0 allows an HTML-profile carrier (`kc:*` meta tags
  instead of YAML). The bump line and Step 4 checklist are MD-only, so an
  HTML-profile doc can be edited without bumping `kc:updated`, leaving a stale
  timestamp the dashboard / staleness audit reads as current.

Proposal governance applies (classify → PROPOSAL_REQUIRED): touches packaging
policy (what the installer ships to every consumer) and the skill system
(`learn.md`).

## Scope

1. **#97 — relocate maintainer-only tests.** `git mv` both offenders from
   `governance_core/tools/` to `maintainer/`:
   - `governance_core/tools/test_curate_gate.py` → `maintainer/test_curate_gate.py`
   - `governance_core/tools/test_candidate_intake.py` → `maintainer/test_candidate_intake.py`
   Each computes `REPO_ROOT = Path(__file__).resolve().parent.parent`; both
   `tools/` and `maintainer/` sit one level under the repo root, so the move
   needs **no logic change** — `parent.parent` still resolves to the repo
   root and `sys.path.insert(REPO_ROOT/"maintainer")` still finds the module.
   Update each docstring's "Run from repo root: python tools/..." line to
   `python maintainer/...`. `maintainer/` is committed source that the
   installer does **not** materialize (not in `COPY_CATEGORIES`), so the
   tests leave the consumer file-set and continue to run on the hub.
2. **#99 — carrier-aware update timestamp in `learn.md`.** Step 3's
   "更新已有文件时" item 3 becomes carrier-aware: **MD** → YAML frontmatter
   `updated:`; **HTML profile** → `kc:updated` meta content (and sync
   `kc:status` if status changed). Add a Step 4 note that for HTML-profile
   docs the frontmatter checklist maps onto the `kc:*` meta set
   (title/owner/status/created/updated/tags), per `knowledge-html-profile.md`.

## Non-Goals

- **Not** adding an installer exclusion-list / dev-extra mechanism for
  maintainer tests. Relocating to `maintainer/` (co-located with the code
  under test, already excluded from packaging) is structural and needs no
  list to keep in sync — a list would be a new drift surface.
- **Not** moving `test_auth_guard.py` / `test_renewal.py` — they import only
  distributed `governance_core` and are consumer-safe by design (they
  gracefully handle an absent `maintainer/`).
- **Not** changing `curate_gate` / `candidate_intake` logic, the candidate
  pipeline, or the `learn` carrier-decision (Step 0) itself — only the
  update-timestamp discipline (Step 3/4).
- **Not** touching constitution / contracts.

## Guardrails

- **edit-write-guard**: edits to `governance_core/tools/*` (moved),
  `maintainer/*` (committed source), `governance_core/commands/learn.md`
  (skill body — a command, not a constitution file, so no Art.13 block).
- **command-guard**: `git mv`, `governance-core upgrade`, `tools/test_*.py`,
  `python -m build`; avoid denied `rm -rf`/redirect literals.
- **boundary-guard**: all targets inside the repo.
- **Art.11 (source/autonomy)**: edit package source; `upgrade --project-root .`
  re-materializes and (with prune) drops the old `tools/` copies. `maintainer/`
  is not an autonomy-layer copy category — it is committed in place.

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal approved. No constitution change (both are
  implementation/skill-body fixes, not new clauses).
- Validation: `submit` → user `approve`.
- Exit criteria: status `approved`.

### Phase 1: #97 — relocate maintainer-only tests

- Deliverables: `git mv` the two test files to `maintainer/`; update their
  docstring run-path lines; `upgrade --project-root .` prunes the stale
  `tools/test_curate_gate.py` / `tools/test_candidate_intake.py` autonomy
  copies.
- Validation: both tests pass from `maintainer/` on the hub; a consumer-sim
  check — neither file is in the install file-set / wheel; grep confirms no
  remaining `governance_core/tools/test_*.py` imports a `maintainer/` module.
- Exit criteria: consumer file-set ships zero maintainer-importing tests.

### Phase 2: #99 — carrier-aware learn.md update timestamp

- Deliverables: Step 3 item 3 rewritten carrier-aware; Step 4 HTML-profile
  note added.
- Validation: re-read learn.md — MD and HTML carriers both have an explicit
  timestamp-bump path; wording consistent with `knowledge-html-profile.md`.
- Exit criteria: the two carriers are symmetric on update-timestamp hygiene.

### Phase 3: Dogfood + close-out

- Deliverables: `upgrade --project-root .`; run full hook + tools test
  suites (incl. the relocated tests from `maintainer/`); build + inspect
  wheel; STATE.md before the phase commit; version bump; close #97 + #99.
- Validation: all suites green; wheel top-level `governance_core*` only and
  excludes the two relocated tests; `governance-core doctor` exit 0.
- Exit criteria: implemented + both issues closed referencing the commit;
  0.30.0 released (separate human-approved outward step).

## Approval Criteria

- Reviewer agrees relocating to `maintainer/` (vs an installer exclusion
  list) is the right structural fix for #97, and that exactly the two
  import-time offenders move (not the two comment-only false matches).
- Reviewer agrees the move needs no code-logic change (`parent.parent`
  invariant) and the hub still runs the tests from `maintainer/`.
- Reviewer agrees the #99 edit is a carrier-aware clarification only, with no
  change to the Step 0 carrier decision.

## Validation Plan

- `python maintainer/test_curate_gate.py` and
  `python maintainer/test_candidate_intake.py` → pass on the hub.
- `grep -rn 'parent / "maintainer"\|"maintainer")' governance_core/tools/test_*.py`
  → empty (no tools test imports maintainer after the move).
- Build wheel; assert `test_curate_gate.py` / `test_candidate_intake.py` are
  NOT in `governance_core/tools/` within the wheel; top-level `governance_core*`
  only; no `maintainer/` leak.
- Full suites: script-style per-file + `pytest tools/`; `upgrade` + `doctor`
  exit 0.
- Re-read `learn.md` Step 3/4 for carrier symmetry.

## Rollback / Recovery

- Per phase: `git mv` is reversible (move back); `learn.md` edit is a `git
  revert` of the package-source commit + `upgrade --project-root .`.
- No data migration; no irreversible state. The relocation only changes which
  directory holds the tests, not their behavior.

## Risks

- **Hub loses sight of the relocated tests** (med prob, low impact): the test
  sweep enumerates `tools/test_*.py`; after the move the two live in
  `maintainer/`. Mitigation: run them explicitly in Phase 3 validation; note
  in STATE that maintainer tests run from `maintainer/`.
- **Stale build cache hides the removal** (low): per memory
  `stale-build-lib-cache-masks-file-removal`, `rm -r build` before
  `python -m build` and re-inspect the wheel so the dropped tools tests
  don't linger from `build/lib`.
- **Upgrade prune surprises** (low): `upgrade` (default prune) removes the
  old `tools/` copies; `--dry-run` first to confirm only those two are
  pruned, no unrelated file.
- **learn.md wording drift vs knowledge-html-profile.md** (low): cross-check
  the `kc:*` meta names against that doc when editing.

## State Log

- 2026-06-16: draft created by core agent (P-0102)
- 2026-06-16: draft → pending (submit for review: relocate 2 maintainer-only tests (#97) + carrier-aware learn.md update timestamp (#99))
- 2026-06-16: pending → approved (user approval signal: 批准)
- 2026-06-16: approved → in-progress (begin Phase 1: relocate maintainer-only tests)
- 2026-06-16: in-progress → implemented
