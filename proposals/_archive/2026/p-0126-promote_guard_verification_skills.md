---
id: P-0126
agent: core
status: implemented
created: 2026-10-09
approved_at: 2026-10-09
implemented_in: b38ed12
implemented_at: 2026-10-09
owner: core
---

# Proposal P-0126: Promote candidates #142 + #140: verify-guard-fires-in-its-target-context and gate-on-change-content-not-target-path (genericized guides)

## Trigger

Hub curation of the 2026-10-09 candidate backlog (10 open issues, 5 unique
candidates). Two of them are in-charter governance/enforcement skills from
trade-agent, both `kind: skill`, `layer: candidate-common`:

- **#142** `verify-guard-fires-in-its-target-context` (revised text; #141/#144/#146
  were the earlier version and are closed as duplicates).
- **#140** `gate-on-change-content-not-target-path` (#143/#145 byte-identical
  re-files, closed as duplicates).

The owner directed the backlog plan be executed (2026-10-09). Adding skills to the
package skill system ships to every consumer via `upgrade` — curate-candidate
step 8 + classify ("改 skill 体系") make it PROPOSAL_REQUIRED.

## Current State (read, not assumed)

- `governance_core/skills/` holds 20 `.md` files (18 guides + `README.md` +
  `_template.md`); none covers either candidate. Grep for `inert` /
  `registered.*running` / `exit code` across the directory hits only
  `external-design-reverse-feed.md` (unrelated context). Net-new.
- Nearest neighbour: `quality-gate-checks-form-human-judges-substance.md:1-16`
  is about WHAT a gate may judge (form vs substance). #140 is the orthogonal
  question of WHICH INPUT DIMENSION a gate keys on (target path vs change delta);
  #142 is about whether a gate RUNS at all. Complementary, no overlap.
- Both candidates describe failure modes governance-core's own hooks are exposed
  to, so the guides are dogfoodable:
  - root-sensitivity (#142 step 3): `governance_core/hooks/_guard_common.py:31`,
    `auth-guard.py:190`, `command-guard.py:81`, `data-source-guard.py:116` all
    derive `repo_root` from `Path(__file__).resolve().parent.parent.parent`.
  - path-dimension gating (#140 step 1): `governance_core/hooks/edit-write-guard.py:635-644`
    decides on `tool_input.get("file_path")` only.
- Topology: `governance_core/skills/lesson-classification.md:24-27` — a
  self-hosted package project authors a promoted skill as a **guide** in the
  package source; payloads arrive `type: learned` and must be converted
  (precedent P-0114, P-0110).
- Version is `0.42.1` (`pyproject.toml:7`, `governance_core/__init__.py:6`).
- Consumer-domain residue in the payloads (read in full from the issue bodies,
  comments checked — intake comment only, no submitter correction):
  - #142: "measured 2026-08-20, two dead absolute registrations sat next to one
    live variable-based registration" (a dated consumer anecdote); multi-clone
    wording ("per-clone hook", "the sync tool", "across all clones").
  - #140: "beat a naive path regex by 93 hits to 0 in this case" (consumer
    measurement); "(for governance-core consumers: .governance/installed_files.json)"
    is hub-relevant and stays.

## Scope

- ADD `governance_core/skills/verify-guard-fires-in-its-target-context.md` and
  `governance_core/skills/gate-on-change-content-not-target-path.md` — payloads
  transformed to house-style guides (`type: guide`, drop `layer:`, add
  `theme: universal` / `owner: core`), workflow verbatim, illustrations genericized.
- Record both curation decisions (`promoted`) in `maintainer/consumer_registry.json`
  via `registry.record_candidate` (not `candidate.py promote`, which would re-copy
  the raw payload over the genericized file).
- Add digest-keyed "already promoted" advisories to
  `governance_core/candidates/rejected_registry.json` for every payload version
  seen (`block_by_name: false`), so consumer sweeps stop re-filing byte-identical
  copies while a genuinely revised skill can still be offered.
- Version bump 0.42.1 → 0.43.0. Close #142 and #140 with the curation outcome.

## Design & Contract

> Documentation/skill add. No code interface or data-flow change.

### Interfaces, I/O & Realization
- **Capability**: two recallable guides. **Realizer (end-to-end)**: guide file in
  `governance_core/skills/` → copied to `.claude/skills/` by `installer.py` on
  `upgrade` → scanned by `governance_core/discovery/registry.py` → name +
  description injected at SessionStart by `session-context.py` → body lazy-loaded
  via the Skill tool. No new function / CLI / endpoint.
- **Mutation**: two ledger appends, performed by the maintainer (core agent) at
  curation time through `registry.record_candidate` and a hand-authored
  `rejected_registry.json` entry of the existing shape.

### Field Dictionary
N/A — no new field crosses a code boundary. The guides expose only frontmatter
`name` / `description` / `theme` to the existing registry scan; the ledger
entries reuse the existing `consumer_registry.json` / `rejected_registry.json`
record shapes unchanged.

### Flow
issue payload (#142 / #140) → hub transform (learned→guide, genericize) →
`governance_core/skills/*.md` → `upgrade` / installer → `.claude/skills/*.md` →
registry inject → agent SessionStart context.

## Non-Goals

- No hook change: this proposal does NOT add a content-signal layer to
  `edit-write-guard` nor a registration self-test to `doctor`. The guides are
  method, not mechanism; any hub mechanism they motivate is a separate proposal.
- No fix for the duplicate re-filing pipeline itself (intake digest dedup, sweep
  hub-check) — separate proposal, next in the backlog plan.
- No `prompt-context-router` keyword registration.
- Publishing the release (GitHub Release → PyPI) is not part of implementation;
  it needs explicit human confirmation (core-A3).

## Open Questions

None.

## Alternatives & Rationale

- **Promote verbatim** — rejected: dated consumer measurements read as facts
  about the reader's own repo; genericizing illustrations is the curate-candidate
  step-3 rule.
- **Promote #141's shorter text for verify-guard** — rejected: #142 adds the
  "enumerate every registration before concluding" step, which is exactly the
  guard against the skill's own false-positive ("this guard is inert" when a
  healthy registration sits beside a dead one).
- **Merge the two into one guide** — rejected: different triggers (auditing
  whether a guard runs vs a guard that runs but keeps being bypassed); separate
  descriptions match better at recall time.
- **Advisory with `block_by_name: true`** (the P-0114 follow-up precedent) —
  rejected here: #142 itself was a legitimate revision of #141 filed the same
  day; name-blocking would have suppressed it. Digest-keyed entries block only
  byte-identical re-files.
- **Chosen**: two genericized guides + digest-keyed advisories.

## Guardrails

- `edit-write-guard`: new files under `governance_core/skills/` (package source),
  not the constitution trio — allowed. Autonomy-layer copies are not hand-edited
  (Art.11.2); they are refreshed by `upgrade`.
- `boundary-guard`: all writes in-repo.
- Package isolation (Art.11.4): `governance_core/skills/*.md` is an
  already-globbed package-data dir; wheel-content check confirms inclusion and
  no `maintainer/` leak.

## Phases

### Phase 1: Author, record, validate

- Deliverables: two guides; registry + advisory entries; version 0.43.0;
  issues #142 / #140 closed with outcome.
- Validation: see Validation Plan.
- Exit criteria: all validation green; decisions recorded; issues closed.

## Approval Criteria

- [ ] Field Dictionary is N/A and says why — human-verify: no new cross-boundary field introduced
- [ ] Every capability / mutation has a named realizer — human-verify: discovery chain + maintainer ledger writes named above
- [ ] Open Questions resolved — human-verify: section reads None
- [ ] Both guides exist in package source with guide frontmatter — cmd: python -c "import pathlib,sys; ok=all('type: guide' in pathlib.Path('governance_core/skills/'+n+'.md').read_text(encoding='utf-8') and 'layer:' not in pathlib.Path('governance_core/skills/'+n+'.md').read_text(encoding='utf-8').split('---')[1] for n in ('verify-guard-fires-in-its-target-context','gate-on-change-content-not-target-path')); sys.exit(0 if ok else 1)"
- [ ] No dated consumer anecdote survives — cmd: python -c "import pathlib,sys; t=''.join(pathlib.Path('governance_core/skills/'+n+'.md').read_text(encoding='utf-8') for n in ('verify-guard-fires-in-its-target-context','gate-on-change-content-not-target-path')); sys.exit(1 if ('2026-08-20' in t.split('---',2)[2] or '93 hits' in t) else 0)"
- [ ] Registry lists both guides — cmd: python -c "import subprocess,sys; o=subprocess.run([sys.executable,'-m','governance_core.discovery.registry','--format','table'],capture_output=True,encoding='utf-8').stdout; sys.exit(0 if 'verify-guard-fires' in o and 'gate-on-change-content' in o else 1)"
- [ ] Self-install is healthy after upgrade — cmd: governance-core doctor
- [ ] Wheel contains both guides, top-level is governance_core only — human-verify: wheel listing inspected after a clean build

## Validation Plan

1. `python -m governance_core.discovery.registry --format table` — both listed.
2. `governance-core upgrade --project-root .` then `governance-core doctor` — exit 0.
3. Test suites: `pytest tools/` plus the script-style suites touching candidates
   (`tools/test_candidate_sweep.py`, `tools/test_candidate_recovery.py`) — the
   advisory entries must not break registry loading.
4. Clean `build/`, `python -m build --wheel`, inspect: top-level `governance_core*`
   only, both guides present, no `maintainer/`.

## Rollback / Recovery

Delete the two guide files, revert the version bump, drop the two
`consumer_registry.json` entries and the advisory entries. Purely additive; a
guide only adds a name + description to SessionStart context.

## Risks

- **Injection token cost** (low): two more universal name+description lines.
  Mitigation: descriptions lead with the trigger and stay short.
- **Advisory mis-blocks a revision** (low): entries are digest-keyed with
  `block_by_name: false`, so only byte-identical payloads are suppressed.
- **Multi-clone wording irrelevant to single-agent consumers** (low): genericized
  to "each copy / each install" where the mechanism does not depend on clones.

## State Log

- 2026-10-09: draft created by core agent (P-0126)
- 2026-10-09: draft → pending (submit for review: promote #142 + #140 as genericized guides)
- 2026-10-09: pending → approved (user approval 2026-10-09: '按你的建议逐项完成这些工作' (reply to the plan asking whether to execute step 1 and open the step-2 promote proposal))
- 2026-10-09: approved → implemented (reconcile: candidate.py named in scope only as the tool NOT used; STATE.md + version files are the expected bump/wrap-up touch -- no substantive deviation)
