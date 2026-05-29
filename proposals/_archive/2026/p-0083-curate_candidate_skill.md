---
id: P-0083
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: 3aa8f69
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0083: Add /curate-candidate command skill (hub-side curation workflow)

## Trigger

This session ran the hub-side candidate-curation workflow **6 times** (P-0078,
P-0079, the #8/#9 reject, P-0080, plus the #12/#13/#14 triage); the
skill-discovery tracker has flagged `--should-extract = YES` (complexity ≥ 7)
throughout. The workflow is reusable and currently lives only in maintainers'
heads + scattered across core-manual §11. Package it as a `/curate-candidate`
command skill — the hub-side counterpart to `/submit-candidate`. Adds to the
skill system + ships to all consumers → proposal governance (as P-0073's
`/upgrade`). Note: for a self-hosted hub, a learned skill in the gitignored
`.claude/skills/learned/` would be clobbered by `upgrade`; the correct home is a
**packaged command skill** in `governance_core/commands/`.

## Scope

One new file: **`governance_core/commands/curate-candidate.md`** — an
orchestration command skill (frontmatter `theme: universal, owner: core`, like
`/upgrade`). It encodes the workflow as a checklist that **points to** the
authoritative tools/docs without duplicating them (Art.99 skill single-source):

1. **Review** — `python tools/candidate.py review` (local envelopes + open
   GitHub `candidate` issues).
2. **Classify** each candidate — generic common-layer vs domain-specific (defer
   to the `lesson-classification` skill); net-new vs already-in-source; and
   **completeness** (all payloads attached? — the #14 incomplete-bundle case →
   request the missing files, keep the issue open).
3. **Verify before applying** (the hard-won technical core):
   - Fetch the issue body; extract `candidate.json` + payload(s).
   - **Drift candidates**: compare `baseline_sha256` to the current package
     source (`sha256sum governance_core/<path>`). Equal → applies clean; drifted
     → `git apply -p1 --recount` (re-locates hunks by context). For full-file
     payloads, diff with `git diff --no-index --ignore-cr-at-eol` to strip the
     CRLF-vs-LF noise and see the true (often pure-add) delta.
   - **De-trade-ify**: if the mechanism is generic but examples leak a consumer's
     domain, genericize the examples before shipping (the #11 case).
4. **Apply to `governance_core/` package source ONLY** (Art.11.2) — never the
   autonomy-layer copy.
5. **New hook?** register it in `hooks/hooks_manifest.json` and honor
   `runtime-import-discipline.md` (self-contained, or guard the import + fail
   open). **New non-.py data file?** add it to `pyproject` `[tool.setuptools.
   package-data]` or it silently drops from the wheel — the editable install
   masks this; only the **wheel-content check** catches it (the P-0080 case).
6. **Version bump** + tests + `governance-core upgrade --project-root .` dogfood
   + `governance-core doctor` exit 0 + **wheel isolation check** (top-level only
   `governance_core*`, the new files present, `maintainer/` absent).
7. **Record the decision** — `candidate.py promote <env> --decision
   promoted|rejected` (for mechanisms, place by hand then record); or
   `maintainer/reject_candidate.py --issue N --reason … --advice … --also-close`
   for a reject-with-advisory.
8. **Promotions that add capability go through `/proposal`** (classify → create →
   approve → implement → archive).
9. **Close the issue** with a curation-outcome comment (thank the contributor;
   for incomplete bundles, request the rest and keep open).

## Non-Goals

- Not re-implementing `candidate.py` / `reject_candidate.py` — the skill
  orchestrates the existing tools (single source of truth).
- Not duplicating core-manual §11 or `runtime-import-discipline.md` /
  `lesson-classification` content — point to them.
- No change to the consumer-side `/submit-candidate` or the candidate pipeline
  code.

## Guardrails

- **edit-write-guard**: new file is `governance_core/commands/curate-candidate.md`
  (package source) — not `CLAUDE.md`/`constitution/*`.
- **Art.99 skill single-source**: the skill references tools/docs as pointers; it
  must not restate their internal steps verbatim (drift risk).
- **Art.11.4**: new `.md` under `governance_core/commands/` ships via the
  existing `commands/*.md` package-data glob — wheel stays `governance_core*`.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — adding a skill file is not a constitution/contract edit.

### Phase 1: Author the skill + ship

- Deliverables:
  - Write `governance_core/commands/curate-candidate.md`.
  - Bump 0.16.0 → 0.17.0.
  - `governance-core upgrade --project-root .` → the command lands in
    `.claude/commands/` and is discovered by the registry.
  - wheel 0.17.0 isolation; full `tools/test_*.py` green (no code change, but run).
- Validation: see Validation Plan.
- Exit criteria: skill present in package source + installed; discovered by
  `python -m governance_core.discovery.registry`; doctor exit 0; wheel isolated.

## Approval Criteria

- Reviewer agrees the workflow is worth packaging as a command skill and that the
  checklist is accurate (it mirrors what this session actually did).
- Reviewer accepts the packaged-command home (not gitignored learned/).

## Validation Plan

- `governance-core upgrade --project-root .` exit 0; `.claude/commands/
  curate-candidate.md` present.
- `python -m governance_core.discovery.registry --format table` lists
  `curate-candidate` (so `/curate-candidate` is invocable).
- Full `tools/test_*.py` green (no code touched; regression check).
- `governance-core doctor` exit 0.
- wheel 0.17.0: top-level only `governance_core*`; `commands/curate-candidate.md`
  present; `maintainer/` absent.

## Rollback / Recovery

- Pre-commit: `git checkout -- governance_core/commands/curate-candidate.md`.
- Post-commit: `git revert <hash>`; re-run `upgrade`. Doc-only, additive — pure
  revert, no state/schema impact.

## Risks

- **Skill drifts from the tools it points to** (low): mitigated by keeping it a
  pointer-style checklist (Art.99), not a restatement.
- **Checklist incompleteness** (low): it is distilled from 6 real runs this
  session; future curation refines it via `/update-skill`.
- **Version bump** 0.16.0 → 0.17.0.
- **Ceremonial-proposal critique** (accepted): single-agent; weight is the
  all-consumer blast radius + capturing a repeatedly-used workflow.

## State Log

- 2026-05-29: draft created by core agent (P-0083)
- 2026-05-29: draft → pending (submit /curate-candidate command skill (hub-side curation workflow, distilled from 6 runs this session))
- 2026-05-29: pending → approved (user signal: 批准)
- 2026-05-29: approved → implemented
