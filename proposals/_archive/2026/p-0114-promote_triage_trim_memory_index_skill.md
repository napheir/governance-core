---
id: P-0114
agent: core
status: implemented
created: 2026-07-01
approved_at: 2026-07-01
implemented_in: fd5939e
implemented_at: 2026-07-01
owner: core
---

# Proposal P-0114: Promote candidate #121 triage-and-trim-bloated-memory-index skill (genericized guide)

## Trigger

Candidate issue #121 (`triage-and-trim-bloated-memory-index`, from trade-agent,
`kind: skill`, `layer: candidate-common`). During hub curation the owner chose
**promote** (AskUserQuestion, 2026-07-01). Adding a skill to the governance-core
skill system is a capability add that ships to all consumers via `upgrade` —
curate-candidate step 8 + classify ("改 skill 体系") make it PROPOSAL_REQUIRED.

## Current State (read, not assumed)

- `governance_core/skills/` holds 18 skills; **every one is governance / harness /
  meta** (e.g. `memory-staleness-policy.md`, `skill-injection-tiers.md`,
  `lesson-classification.md`, `constitution-iteration-decision-tree.md`). None is a
  business-domain skill — the candidate fits this charter.
- `governance_core/skills/memory-staleness-policy.md:9-16` governs memory by a
  **time** axis (project 7d / reference 30d). The candidate is the orthogonal
  **size** axis — bounding the always-injected `MEMORY.md` index — and its Notes
  explicitly state "staleness 治不了无界增长". Net-new, complementary, no overlap.
- `governance_core/skills/skill-injection-tiers.md:38-52`: guides are tier B
  (SessionStart injection via `session-context.py`), auto-scanned by
  `governance_core/discovery/registry.py` from `.claude/skills/*.md`. A new guide
  needs NO manifest edit — the registry scan surfaces it.
- Topology (P-0068, `lesson-classification.md:49-56`): in a self-hosted package
  project a promoted skill is authored as a **guide** in the package source
  (`governance_core/skills/`), not a `learned` skill. The candidate payload is
  `type: learned` and must be converted.
- The candidate body carries no consumer-domain leak (no tickers/paths/proposal
  ids); it is already generic and bilingual, matching `memory-staleness-policy.md`.

## Scope

- ADD `governance_core/skills/triage-and-trim-bloated-memory-index.md` — the
  candidate payload transformed to a house-style **guide** (`type: guide`, drop
  `layer:`, add `theme/owner/tags`, body verbatim).
- Record the curation decision (`promoted`) in `maintainer/consumer_registry.json`
  via `registry.record_candidate` (NOT `candidate.py promote` — hand-transformed
  payload would be clobbered; see lesson `curate-promote-clobbers-genericized-payload`).
- Version bump (ships via `upgrade`). Close issue #121 with a thank-you.
- NOT in scope: the funnel `loaded`-counter work (candidate seam) — see #122,
  handled as a separate proposal (cross-linked below).

## Design & Contract

> Documentation/skill add. No code interface or data-flow change; the "realizer" is
> the skill-discovery chain, named below.

### Interfaces, I/O & Realization
- **Capability**: an actively-recallable guide for bounding a bloated native memory
  index. **Realizer (end-to-end)**: the guide file `governance_core/skills/
  triage-and-trim-bloated-memory-index.md` → installed to `.claude/skills/` by
  `installer.py` on `upgrade` → scanned by `discovery/registry.py`
  (`manifest_for_injection`, tier B) → injected name+description at SessionStart by
  the `session-context.py` hook → body lazy-loaded on demand via the Skill tool.
  No new function/CLI/endpoint; the discovery chain already exists.
- **Field Dictionary**: N/A — no field crosses a code boundary; the artifact is a
  static Markdown guide consumed by the registry scan (frontmatter `name` +
  `description` only, already governed by the registry's own scan contract).

### Flow
contributor skill (issue #121 payload) → hub transform (learned→guide) →
`governance_core/skills/*.md` (source) → `upgrade`/installer → `.claude/skills/*.md`
→ registry tier-B inject → agent SessionStart context.

## Non-Goals

- No `prompt-context-router` / `INDEX.routing.json` keyword registration (tier-B
  SessionStart injection is sufficient; router keywords can be a later enhancement).
- No shipping of a `memory_lint.py` tool — the guide references such a linter
  illustratively; it is not a deliverable here.
- No change to `memory-staleness-policy.md` or Art.16 (orthogonal time axis).
- The #122 funnel `loaded`-counter is a separate proposal; this guide's B1
  graduation gate ("closure check 确认 surface 可达 再 drop native") is the *policy*
  that #122's counter will later let a consumer verify *empirically*.

## Open Questions

None. (Body kept verbatim including the illustrative `memory_lint.py` mention;
frontmatter converted learned→guide per topology.)

## Alternatives & Rationale

- **Reject as out-of-charter** — rejected: unlike #120 (data-engineering), this is a
  governance/memory-hygiene mechanism squarely in governance-core's charter, and
  governance-core dogfoods a native `MEMORY.md` itself.
- **Promote as a `learned` skill (verbatim)** — rejected: P-0068 topology says a
  self-hosted package promotes to a **guide** in package source; `learned` skills are
  per-agent session extractions kept in `.claude/skills/learned/`.
- **Promote as a guide (chosen)** — matches the 18 existing common-layer guides and
  the P-0079 / P-0098 / P-0100 promote-genericized-skill precedents.

## Guardrails

- `edit-write-guard`: the new file is under `governance_core/skills/` (package
  source), not the constitution trio — Edit/Write allowed.
- `boundary-guard`: all writes in-boundary (repo).
- Package isolation (Art.11.4): `governance_core/skills/*.md` already ships; the new
  `.md` sits in an already-globbed dir — wheel-content check confirms inclusion +
  no `maintainer/` leak.

## Phases

### Phase 1: Author, wire, validate, record

- Deliverables:
  - `governance_core/skills/triage-and-trim-bloated-memory-index.md` (guide).
  - Version bump; `consumer_registry.json` decision = `promoted`.
  - Issue #121 closed with curation-outcome + thanks.
- Validation:
  - `registry.py --format table` lists the new guide with its description.
  - `governance-core upgrade --project-root .` + `doctor` exit 0.
  - Wheel-content: `python -m build --wheel`; top-level only `governance_core*`,
    new guide present, no `maintainer/`.
- Exit criteria: all validation green; decision recorded; issue closed.

## Approval Criteria

- [ ] New guide has house-style frontmatter (theme/name/description/type:guide/tags)
      and a registry-matchable description leading with the trigger pattern.
- [ ] Field Dictionary is N/A (no cross-boundary field) — realizer named (discovery chain).
- [ ] Open Questions resolved (None).
- [ ] Curation decision recorded via `registry.record_candidate` (not `promote`).
- [ ] Wheel includes the guide; `maintainer/` absent; top-level `governance_core*` only.
- [ ] Cross-link to #122 recorded (policy↔instrument seam).

## Validation Plan

1. `python -m governance_core.discovery.registry --format table` — guide listed.
2. `governance-core upgrade --project-root .` then `governance-core doctor` — exit 0.
3. `python -m build --wheel` + inspect wheel top-level + presence + `maintainer/` absence.
4. Existing test suites remain green (no code change; doc-only add).

## Rollback / Recovery

Delete `governance_core/skills/triage-and-trim-bloated-memory-index.md`, revert the
version bump, and drop the `consumer_registry.json` entry. Pure additive; no runtime
risk (a guide only adds a name+description to SessionStart context).

## Risks

- **Index-injection token cost** (low): one more tier-B name+description at
  SessionStart (~30 tokens). Mitigation: description ≤ 200 chars per house rule.
- **Charter-creep precedent** (low): promoting a memory-hygiene guide is squarely
  in-charter; the #120 reject in the same batch draws the business/governance line.

## State Log

- 2026-07-01: draft created by core agent (P-0114)
- 2026-07-01: draft → pending (submit for review: promote #121 as genericized guide)
- 2026-07-01: pending → approved (user approval: 批准实施 (AskUserQuestion 2026-07-01))
- 2026-07-01: approved → implemented
