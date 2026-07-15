---
id: P-0123
agent: core
status: implemented
created: 2026-07-15
approved_at: 2026-07-15
implemented_in: 2305ccc
implemented_at: 2026-07-15
owner: core
---

# Proposal P-0123: First-class terminal status for hub-upstreamed proposals

## Trigger

GitHub issue #136. governance-core's candidate/uplink pipeline carries a consumer's
capability up to the hub. When that capability originated as a **consumer proposal**,
the consumer is left with a proposal that is genuinely terminal — its replacement now
lives in governance-core — but the proposal schema has **no terminal status that can
express it**. The state is produced by governance-core's *own* mechanism, so the fix
is a hub concern. Proposal governance applies because this changes a `contracts/` file
(the frontmatter schema) plus its install-managed validator and writer, shipped to
every consumer (Art.3 契约机制, Art.11 单一权威源).

Chosen shape (per user, 2026-07-15): **shape B** from the issue — a first-class
terminal status — over shape A (overload `superseded_by` with an external ref). B keeps
`superseded` meaning *local* replacement and gives the uplink pipeline a natural place
to stamp provenance.

## Current State (read, not assumed)

- **Enum has no external-supersession terminal state.** `contracts/proposal_frontmatter_schema.md`
  §3.1 (lines 71–79) lists terminal statuses `implemented` / `superseded` / `rejected`
  only. §4.4 (lines 114–118) defines `superseded_by` as a **relative path** to a
  replacement proposal; §5.3 (lines 154–161) forbids anything but a repo-root-relative
  `proposals/…` path; §7 (lines 219–221) requires the target to exist *and* carry a
  `supersedes:` back-reference.
- **The validator enforces that locality hard.** `governance_core/tools/audit_proposals.py`
  Check 6 (lines 217–239): `target = repo_root / fm["superseded_by"]`; if
  `not target.is_file()` → FAIL `points to non-existent file`, else it parses the target
  and requires this file in the target's `supersedes` list. A cross-repo `<repo>:<path>`
  ref is nowhere in the schema, so it stats as a missing local file → **permanent,
  unclearable FAIL**.
- **The writer's state machine is closed over the same 7 statuses.**
  `governance_core/tools/proposal_lib.py:232–244`: `VALID_STATUS` (7 values),
  `TERMINAL_STATUS = {implemented, rejected, superseded}`, `ALLOWED_TRANSITIONS`.
  `transition_proposal` (`:1252–1255`) has a `superseded` branch requiring
  `--superseded-by`; supersede is allowed from any state (`:1172–1173`). Archive year
  derivation (`:1338–1344`) maps each terminal status to a date field
  (`implemented→implemented_at`, `rejected→rejected_at`, `superseded→approved_at`).
- **The state is reachable only via the uplink pipeline** — `governance_core/tools/candidate.py`
  + `governance_core/commands/submit-candidate.md` (consumer side) + `/curate-candidate`
  (hub side). Promotion happens on the **hub**; the proposal that becomes terminal lives
  in the **consumer** tree. No component today writes the consumer's proposal after a
  promotion.
- The whole subsystem (schema contract + `proposal_lib.py` + `audit_proposals.py` +
  `/proposal` skill) is install-managed (root autonomy layer is a snapshot of package
  source per Art.11), so a consumer cannot fix it locally without manufacturing drift
  that `upgrade` reverts.

## Scope

Package source only (`governance_core/`); no consumer-side edits. Files changed:

1. `governance_core/contracts/proposal_frontmatter_schema.md` — new enum value, new
   state-conditional section, new format rule, version bump 1.2.0 → 1.3.0.
2. `governance_core/tools/audit_proposals.py` — enum, `REQUIRED_BY_STATUS`, a new
   format-only check for `upstreamed_to`, `upstreamed_at` in the date set.
3. `governance_core/tools/proposal_lib.py` — enum, `TERMINAL_STATUS`, allow
   `* → upstreamed` (mirror supersede), a `upstreamed` transition branch, CLI
   `--upstreamed-to`, archive date-field map entry.
4. `governance_core/commands/proposal.md` — one `upstream` subcommand row + section.
5. Tests under `governance_core/tools/` covering the three issue acceptance tests.
6. Dogfood `governance-core upgrade --project-root .` so this session runs the new code.

Out of scope: auto-stamping the consumer's proposal from the promote step (see Non-Goals).

## Design & Contract

### Interfaces, I/O & Realization

- **`contracts/proposal_frontmatter_schema.md` (contract, authoritative).** Adds status
  enum member `upstreamed` (terminal); adds §4.x requiring, when `status: upstreamed`,
  the fields `upstreamed_to` (external ref) and `upstreamed_at` (ISO date); adds a format
  rule for `upstreamed_to`. Version → 1.3.0 (minor: new enum value + new conditional
  fields, backward compatible; no grandfathering — no file currently uses the status).
- **`_validate_upstreamed_ref(ref) -> (ok, reason)` (SHARED grammar predicate — the
  single realizer of the format rule).** Lives in `proposal_lib.py` (imported by
  `audit_proposals.py`, matching the existing `current_state_adequacy` /
  `design_contract_adequacy` shared-predicate pattern at `audit_proposals.py:488,524`).
  Matches the regex `^(https?://\S+|[a-z][a-z0-9_-]*:[^\s:]\S*)$`. On failure `reason` is
  ONE actionable message that names both accepted forms and gives a concrete example, e.g.
  `upstreamed_to must be '<repo-slug>:<path>' (e.g. governance-core:proposals/_archive/2026/p-0122-x.md) or an https:// URL; got '<ref>'`.
  Writer and validator call this same function so their verdict and message can never diverge.
- **`proposal_lib.py::transition_proposal(...)` (writer / realizer of the state).** New
  keyword `upstreamed_to: str = ""`. New branch: `elif new_status == "upstreamed":` →
  require `upstreamed_to` (raise if empty) **and** run `_validate_upstreamed_ref`, raising
  the shared actionable message if malformed **before any write** (fail-fast at the CLI so
  the owner fixes it once, never bumps an audit FAIL later); then set
  `fm["upstreamed_to"] = upstreamed_to` and `fm["upstreamed_at"] = today`. `upstreamed`
  added to `VALID_STATUS` + `TERMINAL_STATUS`; transition allowed **from any state** (same
  `pass` branch as `superseded`, since a consumer may upstream from
  draft/pending/approved/in-progress/implemented). CLI parser gains `--upstreamed-to`;
  `--to` choices auto-derive from `VALID_STATUS`. Archive date-map gains
  `"upstreamed": "upstreamed_at"`.
- **`audit_proposals.py` (validator / realizer of the "no local resolution" rule).**
  `VALID_STATUS` gains `upstreamed`; `REQUIRED_BY_STATUS["upstreamed"] = {"upstreamed_to",
  "upstreamed_at"}`; new Check 17: when `status == upstreamed`, call the SHARED
  `_validate_upstreamed_ref` and **stop** — never stat a local file, never look for a
  back-reference (unresolvable across repos by construction, per the issue's stated
  non-goal). `upstreamed_at` joins the Check 7 date set. Check 6 (`superseded`) is
  **untouched** — local supersession keeps its must-exist + back-reference semantics (no
  regression). (This is a defence-in-depth backstop; a bad ref is already rejected at
  write time, so audit only re-catches a hand-edited file.)
- **`/proposal upstream <id> --to-hub <ref>` (skill, user-facing capability).** Realizer:
  the CLI above. `commands/proposal.md` documents it as the terminal transition for a
  proposal whose replacement landed in the hub. Provenance (the hub ref) is recorded on
  the consumer's proposal; audit stays clean.
- **Uplink auto-stamp: deferred (Non-Goals).** The promote step runs on the hub and
  cannot write the consumer's tree; the honest realizer would be the consumer's
  `/submit-candidate` flow offering the transition after it learns the hub URL. Phase 1
  ships the manual transition; auto-wiring is a follow-up.

### Field Dictionary

Governing contract for all rows: **`contracts/proposal_frontmatter_schema.md`** (this
proposal amends it). No parallel vocabulary is introduced.

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `status` (enum, +`upstreamed`) | string | proposal lifecycle state | `proposal_lib.transition_proposal` | `audit_proposals`, `session-context.py`, `/proposal` | `upstreamed` is terminal; joins {implemented, rejected, superseded} |
| `upstreamed_to` | string | external ref to the replacement in the hub | `proposal_lib` (`--upstreamed-to`) | `audit_proposals` Check 17 (format only) | `<repo>:<path>` (e.g. `governance-core:proposals/_archive/2026/p-0122-x.md`) **or** `https?://…` URL; recorded + format-checked, **not resolved** |
| `upstreamed_at` | ISO date | date the upstreamed transition was stamped | `proposal_lib` (`_today()`) | `audit_proposals` Check 7; archive year | `YYYY-MM-DD`, `≥ created` |

### Flow

```
consumer capability originates as proposal P-NNNN (consumer repo)
   → /submit-candidate  →  hub intake  →  /curate-candidate promote  →  lands in governance_core/ (hub)
   → consumer learns hub ref (path / PR / issue URL)
   → /proposal upstream P-NNNN --to-hub <ref>
        → proposal_lib.transition_proposal(new_status="upstreamed", upstreamed_to=<ref>)
             writes status=upstreamed, upstreamed_to=<ref>, upstreamed_at=today  (+ State Log)
   → audit_proposals Check 17: format-validate upstreamed_to, PASS (no local stat)
   → /proposal archive P-NNNN  →  proposals/_archive/<upstreamed_at year>/  (provenance preserved in git)
```

## Non-Goals

- **Cross-repo bidirectional verification.** `upstreamed_to` is recorded and
  format-checked, never resolved. The hub cannot read the consumer's tree at audit time,
  nor vice-versa — that is the honest limit of a single-repo validator (issue's stated
  non-goal).
- **Auto-stamping the consumer proposal at promote time.** The manual `/proposal upstream`
  transition lands first; wiring `/submit-candidate` to offer it automatically is a
  follow-up, not this proposal.
- **Retiring or narrowing `superseded` / `superseded_by`.** Local supersession semantics
  and Check 6 are unchanged.

## Open Questions

- **RESOLVED (user, 2026-07-15) — `upstreamed_to` grammar + where it is enforced.** Ship
  the regex `^(https?://\S+|[a-z][a-z0-9_-]*:[^\s:]\S*)$` (a URL, or `<repo-slug>:<non-empty-path>`;
  rejects a bare `proposals/x.md`, so the hatch cannot launder typos — issue test 3).
  **The owner must not have to repeatedly bump into it.** Therefore the grammar is enforced
  at the **writer** (`transition_proposal` validates `--upstreamed-to` and raises BEFORE
  writing), not only at the validator (Check 17), via ONE shared predicate + ONE shared
  actionable message that NAMES both accepted forms and gives a concrete example. A bad ref
  fails fast at the CLI with a copy-pasteable fix; it never reaches the file to become a
  later audit FAIL.
- **RESOLVED (user, 2026-07-15) — session-context terminal handling: verify at
  implementation.** Phase 2 greps `session-context.py` for any hardcoded terminal/pending
  status set; if it does not derive from `TERMINAL_STATUS`, add `upstreamed` there too so an
  upstreamed proposal drops out of the pending banner. Tracked as a Phase 2 deliverable.

## Alternatives & Rationale

- **Shape A (overload `superseded_by` with an external ref) — rejected by user.** One
  field, one audit branch; cheapest. But it compresses two distinct semantics (local
  replacement vs. cross-repo upstreaming) into one field and one status, and gives the
  uplink pipeline no clean provenance slot. The issue itself argues B is "arguably the
  correct long-term shape."
- **Shape B (this proposal) — chosen.** A first-class terminal status models what actually
  happened, keeps `superseded` meaning local replacement (zero regression to Check 6), and
  gives the uplink mechanism — which the hub already owns — a natural stamping point.
  Cost: enum + one conditional-field section + one new audit branch + one transition
  branch, across contract/validator/writer/skill. Proportionate to a state the hub's own
  mechanism creates.

## Guardrails

- **edit-write-guard** — does NOT block `contracts/`; only blocks the three constitution
  files. This is a contract change, not a constitution edit, so `/iterate-constitution`
  does not apply (Art.13 restricts to CLAUDE.md / total.md / agent.core.md).
- **Package isolation (Art.11.4)** — all edits under `governance_core/`; no new root dir,
  `pyproject.toml packages` still matches `governance_core*`.
- **Dogfood (Art.11.3)** — after editing package source, `governance-core upgrade
  --project-root .` reinstalls so this session's autonomy layer runs the new code.
- **command-guard / boundary-guard** — no new command surface; the `cmd:` acceptance
  tokens below run the test suite, no redirects.

## Phases

### Phase 0: Governance bootstrap

- N/A — this amends `contracts/proposal_frontmatter_schema.md`, not the constitution.
  No `/iterate-constitution` (Art.13 scope is CLAUDE.md / total.md / agent.core.md only).
  The contract's own SemVer + version-history discipline (§8) is the governance path.

### Phase 1: Contract

- Deliverables: `proposal_frontmatter_schema.md` — add `upstreamed` to §3.1 (marked
  terminal); add §4.x (`upstreamed` requires `upstreamed_to` + `upstreamed_at`); add the
  `upstreamed_to` external-ref format rule to §5; add the terminal-invariant line to §7;
  bump Version to 1.3.0 + prepend a version-history entry.
- Validation: `grep` the four sections show the new content; version reads 1.3.0.
- Exit criteria: contract self-consistent; enum, field section, format rule, version all
  present and cross-referenced.

### Phase 2: Validator + writer + tests

- Deliverables: `audit_proposals.py` (enum, `REQUIRED_BY_STATUS`, Check 17 format-only,
  `upstreamed_at` date field, docstring); `proposal_lib.py` (`VALID_STATUS`,
  `TERMINAL_STATUS`, allow `*→upstreamed`, transition branch, `--upstreamed-to` CLI,
  archive date-map); tests covering the three issue acceptance tests.
- Validation: new tests pass; full `audit_proposals.py --root .` stays green; existing
  proposal test suites unregressed.
- Exit criteria: a proposal with `status: upstreamed` + valid `upstreamed_to` audits
  clean; a local `superseded_by` proposal behaves identically to before; a malformed
  `upstreamed_to` FAILs.

### Phase 3: Skill + dogfood

- Deliverables: `commands/proposal.md` — `upstream` subcommand (table row + section +
  anti-pattern note distinguishing it from `supersede`); run `governance-core upgrade
  --project-root .`.
- Validation: `/proposal upstream` documented; `governance version` + a live
  `proposal_lib.py transition --to upstreamed` dry-run works in this session's autonomy
  layer.
- Exit criteria: manual upstream transition drivable end-to-end in this repo.

## Approval Criteria

- [ ] Every Field Dictionary entry names its governing `contracts/` file — human-verify: all three rows cite `contracts/proposal_frontmatter_schema.md`
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: `upstreamed` status ← `transition_proposal`; `/proposal upstream` ← CLI; auto-stamp explicitly deferred in Non-Goals
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: `upstreamed_to` grammar + session-context terminal handling both decided
- [ ] A proposal with `status: upstreamed` + a valid `upstreamed_to` passes audit with no local-file stat — cmd: `python governance_core/tools/test_upstreamed_status.py`
- [ ] Local `superseded_by` behaviour is unchanged (Check 6 no regression) — cmd: `python tools/audit_proposals.py --root .`
- [ ] A malformed `upstreamed_to` still FAILs audit — cmd: `python governance_core/tools/test_upstreamed_status.py`

## Validation Plan

- New `governance_core/tools/test_upstreamed_status.py` (script-style, per the two-suite
  split): (1) upstreamed + valid ref → audit clean, no `is_file` call on the ref; (2)
  local `superseded_by` → must-exist + back-reference still enforced; (3) malformed ref
  → FAIL.
- `python tools/audit_proposals.py --root .` stays green across all three regions.
- Existing suites: `test_proposal_design_contract.py`, `test_proposal_rigor.py`,
  `test_proposal_gates.py`, `test_candidate_*` — unregressed.
- Live dogfood: after `upgrade`, drive `proposal_lib.py transition --id <throwaway>
  --to upstreamed --upstreamed-to governance-core:proposals/x.md` on a scratch proposal.

## Rollback / Recovery

- Per phase: `git revert` the phase commit. The change is additive (new enum value + new
  conditional fields); reverting removes them with no migration — no file uses
  `upstreamed` until a consumer opts in, so there is no orphaned data to reconcile.
- If a consumer already stamped `upstreamed` and the status is reverted, their file would
  fail the enum check — but a revert would only ship in a new package version they choose
  to `upgrade` into, and the field values remain readable prose. Low risk.

## Risks

- **Escape-hatch abuse** (low prob / med impact): a loose `upstreamed_to` grammar could
  launder typos into a clean audit. Mitigation: the Open-Questions regex rejects bare
  paths; issue test 3 pins the malformed-ref FAIL.
- **`session-context.py` hardcoded terminal set drift** (low / low): if it doesn't derive
  from `TERMINAL_STATUS`, an `upstreamed` proposal could linger in the pending banner.
  Mitigation: Open Question 2 — verify at implementation.
- **Divergent `VALID_STATUS` copies** (low / med): the enum lives in *both*
  `audit_proposals.py` and `proposal_lib.py`. Mitigation: Phase 2 changes both in one
  commit; a test asserts both sets contain `upstreamed`.

## State Log

- 2026-07-15: draft created by core agent (P-0123)
- 2026-07-15: draft → pending (submit shape B (first-class upstreamed terminal status) for review, per issue #136)
- 2026-07-15: pending → approved (user approved 2026-07-15 ('批准'); resolved OQ1 (grammar fine but enforce at writer with actionable shared message so owner never repeatedly bumps audit) + OQ2 (verify session-context terminal set at impl))
- 2026-07-15: approved → implemented (as-built: reconcile clean; session-context.py (OQ2 comment) + test_upstreamed_status.py declared in Scope prose, not path tokens; STATE = wrap-up artifact)
