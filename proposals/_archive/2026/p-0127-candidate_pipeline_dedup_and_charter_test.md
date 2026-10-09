---
id: P-0127
agent: core
status: implemented
created: 2026-10-09
approved_at: 2026-10-09
implemented_in: f5cee0a
implemented_at: 2026-10-09
owner: core
---

# Proposal P-0127: Candidate pipeline: hub intake duplicate detection, sweep hub-check on every pending uplink, charter test for candidate-common

## Trigger

The 2026-10-09 backlog (P-0126) showed the candidate pipeline wasting curation
effort in three repeatable ways:

1. **Duplicate re-filing.** 10 open issues were 5 unique candidates
   (`verify-guard-fires-in-its-target-context` x4, `gate-on-change-content-not-target-path`
   x3). The previous round filed `triage-and-trim-bloated-memory-index` 7 times
   (#121 #124 #125 #127 #129 #130 #131). Every duplicate was labeled
   `auto-eligible` by intake.
2. **Out-of-charter candidates.** Of the unique skill candidates since
   2026-06-26, four were rejected as general engineering / business-domain
   (#120, #126, #138, #147) -- all tagged `candidate-common` by the consumer.
3. Hand-closing duplicates does not scale and is the same manual work each round.

Changes hub CI behaviour, a shipped consumer tool (`candidate.py sweep`) and two
shipped skill/command docs -- PROPOSAL_REQUIRED (skill system + automation policy).

## Current State (read, not assumed)

- **Consumer sweep only consults the hub when its ledger is EMPTY.**
  `governance_core/tools/candidate.py:253` guards the self-heal with
  `if envelopes and not led["uplinked"] and shutil.which("gh")`. The ledger is
  `.governance/candidate-outbox/_uplinked.json` -- gitignored, one per clone
  (`governance_core/candidates/ledger.py:10-11`). A clone whose ledger holds ANY
  entry never re-checks the hub, so a skill uplinked from clone A is "pending"
  again in clone B. Evidence the re-files come from different working copies:
  #144 / #146 (08-26, 09-09) carry the OLDER text of the skill, filed after the
  revised #142 (08-20).
- **The hub query already exists and is correct.**
  `ledger.discover_uplinked_from_hub` (`ledger.py:212-272`) lists open + closed
  `[candidate] ... (from <origin>)` issues, re-parses each body with the shared
  parser and returns `{digest, candidate_id, issue_url}`. It discards the issue
  number and state.
- **Hub intake has every byte it needs but does not dedup.**
  `maintainer/candidate_intake.py:1-27` says payload checks "need the payload
  files on disk"; in fact the payload travels in the issue body and
  `ledger.parse_payload_from_issue_body` (`ledger.py:148`) recovers the exact
  bytes (LF-normalized), the same parser `maintainer/reject_candidate.py:122`
  uses to compute the registry sha. Intake's `net-new` verdict
  (`candidate_intake.py:148-160`) only asks whether a target path is tracked at
  HEAD, so every re-file reads `net-new: yes`.
- **Labels**: the repo already has `duplicate` and `dup-of-rejected` (created by
  P-0088, `proposals/_archive/2026/p-0088-candidate_intake_ci_p0082_phase1.md:68`)
  -- `dup-of-rejected` is referenced by no code today. No `revision` label.
- **The tagging rule tells consumers to over-report.**
  `governance_core/skills/lesson-classification.md:79-89`: the test is "would
  another consumer use this unchanged?" and "**When unsure, choose
  `candidate-common`**"; `governance_core/commands/extract-skill.md:20-27`
  repeats it. A domain-agnostic engineering recipe passes that test although the
  hub only curates governance/harness capabilities
  (`governance_core/candidates/rejected_registry.json`, entries for #120 / #126 /
  #138 / #147 all say "out of governance-core charter").
- Workflow permissions (`.github/workflows/candidate-intake.yml:19-21`):
  `issues: write`, `contents: read` -- sufficient to label, comment and close.

## Scope

- `governance_core/candidates/ledger.py` -- add `list_hub_candidate_issues`
  (number + state kept); `discover_uplinked_from_hub` becomes a thin projection
  of it (same return shape, same degradation).
- `governance_core/tools/candidate.py` -- `cmd_sweep`: consult the hub whenever
  there is at least one pending envelope (not only when the ledger is empty),
  merge recovered digests into the ledger, re-filter pending.
- `maintainer/candidate_intake.py` -- compute the payload digest from the issue
  body; classify `dup-of-rejected` / `duplicate` / `revision`; label and comment
  (pointing at the original). Issues are NOT auto-closed in this proposal.
- `governance_core/skills/lesson-classification.md`,
  `governance_core/commands/extract-skill.md` -- replace the over-report rule
  with a two-question test (charter, then genericity).
- `governance_core/commands/curate-candidate.md` -- one paragraph on the new labels.
- Tests: `governance_core/tools/test_candidate_recovery.py`,
  `governance_core/tools/test_candidate_sweep.py`, `maintainer/test_candidate_intake.py`.
- Repo label `revision` (one-off `gh label create`). Version bump 0.43.0 → 0.43.1.

## Design & Contract

### Interfaces, I/O & Realization

**1. `ledger.list_hub_candidate_issues(origin: str, repo: str = UPSTREAM) -> list[dict]`**
(new, package). INPUT: `gh issue list --repo <repo> --state all --search
"[candidate] (from <origin>)" --json number,title,body,url,state --limit 200`.
OUTPUT: one dict per parseable issue -- `number`, `state`, `issue_url`,
`candidate_id`, `title`, `digest`. Unparseable issues are skipped at INFO;
missing `gh` / non-zero exit / non-JSON returns `[]`. Realizer: called by the
consumer's `candidate.py sweep` and by the hub's intake job.
`discover_uplinked_from_hub` keeps its signature and return shape
(`digest` / `candidate_id` / `issue_url`), now derived from this function.

**2. `candidate.py sweep`** (changed, package; realizer = the consumer agent's
`/wrap-up` step 4c running the CLI). After building `pending`: if `pending` is
non-empty and `gh` is on PATH, call `discover_uplinked_from_hub`, `record_uplink`
every recovered entry (idempotent on digest), reload the ledger and drop pending
envelopes whose digest is now recorded. stdout gains one line per skipped
envelope: `sweep: skipping <env> -- already on the hub (<issue_url>)`. The
empty-ledger self-heal becomes a special case of this path and is removed as a
separate branch. No new CLI flag.

**3. `candidate_intake.classify_duplicate(...)`** (new, maintainer; pure, no I/O):

```
classify_duplicate(*, issue_number: int, title: str, digest: str,
                   rejected_registry: dict, prior_issues: list[dict]) -> dict | None
```
Returns `None` (not a duplicate) or
`{"verdict": "dup-of-rejected" | "duplicate" | "revision", "of": [int, ...], "detail": str}`.
Precedence: (a) exact digest match in the shipped `rejected_registry.json`
(via `rejected.is_rejected`, `match == "exact"`) → `dup-of-rejected`; (b) a prior
issue (number lower than this one) with the same digest → `duplicate`; (c) a
prior issue with the same `title`, a different digest, still `OPEN` →
`revision`. Only LOWER-numbered issues count as "prior", so two identical issues
opened together cannot close each other.

**4. `candidate_intake.main()`** (changed; realizer = the `candidate-intake`
GitHub Actions job on `issues.opened`). After metadata validation it computes the
digest and the verdict, then:

| verdict | labels | comment | state |
|---|---|---|---|
| `dup-of-rejected` | `candidate`, `dup-of-rejected` | registry `reason` + `advice` | stays open |
| `duplicate` | `candidate`, `duplicate` | "byte-identical to #N" | stays open |
| `revision` | normal labels + `revision` | "revises open #N (same title, new content)" | stays open |
| none | normal labels | unchanged | stays open |

A flagged duplicate never receives `valid` / `auto-eligible`, so the layer-2
routine cannot promote it, and a maintainer can bulk-close by label
(`gh issue list --label duplicate`). Intake does not close issues itself (see
Open Questions). Any failure in digest computation, registry load or
the hub listing is logged and treated as "no verdict": intake then behaves
exactly as today (fail-open -- dedup is an optimization, labeling is the contract).

**5. Tagging rule** (docs; realizer = the consumer agent following
`/extract-skill` step 2). Two questions, in order:
(Q1 charter) *Is the skill about running the governance / agent harness itself
-- hooks, guards, proposals, memory, skills, constitution, audits, install /
upgrade, agent collaboration?* No → `business`, stop.
(Q2 genericity) *Would a consumer with a completely different business use it
unchanged?* Yes → `candidate-common`; No → `business`.
"When unsure" now resolves per question: unsure on Q1 → `business`; unsure on
Q2 only → `candidate-common`.

### Field Dictionary

No persisted or cross-agent field is added; nothing here is governed by a
`contracts/` file (the candidate envelope contract and the registry record
shapes are unchanged -- N/A for contracts).

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `number` | int | hub issue number | `gh issue list` | `classify_duplicate` | in-memory only |
| `state` | str | hub issue state | `gh issue list` | `classify_duplicate` | `OPEN` / `CLOSED`; in-memory only |
| `digest` | str | payload sha256 (`ledger._hash_payload`, or the body's `payload_sha256` for drift) | shared parser | sweep, intake | 64 hex; same value the uplink ledger and `rejected_registry.json` already store |
| `verdict` | str | intake dedup outcome | `classify_duplicate` | `main()` | `dup-of-rejected` / `duplicate` / `revision`; surfaces only as GitHub labels |

### Flow

```
consumer sweep:  outbox envelopes → local ledger filter → [pending?] → hub issue list
                 → ledger merge → re-filter → uplink only what the hub has never seen
hub intake:      issue opened → metadata validate → body → digest
                 → rejected_registry (exact) → prior issues (digest, then title)
                 → verdict → labels / comment / close
tagging:         /extract-skill step 2 → Q1 charter → Q2 genericity → layer:
```

## Non-Goals

- Reviving / rescheduling the layer-2 curation routine and its kill-switch
  (separate operational step, next in the backlog plan).
- Changing intake's `net-new` verdict or the T0 eligibility rule.
- A hub-side store of seen digests: GitHub issue history is the store.
- Making the consumer ledger shared across clones (the hub check makes it unnecessary).
- Enforcing the charter test mechanically (it stays a judgment made at
  `/extract-skill`; the hub still rejects with advice when it is wrong).
- Publishing a release (needs explicit human confirmation, core-A3).

## Open Questions

- Should a `revision` auto-close the older open issue? Leaning NO (default):
  which text is better is a judgment (#144 / #146 re-filed an OLDER text after
  the revision), so intake only links them.
- Should intake also CLOSE a byte-identical duplicate? DEFERRED to the owner:
  the approved plan was "label as duplicate and point at the original". Closing
  is a one-line follow-up (`gh issue close --reason "not planned"`, permission
  already present) once the labels have proven accurate on real traffic.

## Alternatives & Rationale

- **Fix only the consumer side (sweep hub-check).** Rejected as sole fix: the hub
  cannot trust consumer state, and consumers on an older version keep re-filing
  until they upgrade. Kept as half of the fix because it stops the noise at the
  source and costs one read-only `gh` call per sweep-with-pending.
- **Fix only the hub side (intake dedup).** Rejected as sole fix: every duplicate
  still creates an issue, a CI run and a notification.
- **Share the ledger across clones via git.** Rejected: the outbox is
  deliberately gitignored (it holds unreviewed payload copies); a tracked ledger
  also merges badly.
- **`block_by_name` advisories for every promoted skill** (P-0114 follow-up
  precedent). Rejected as the general mechanism: it suppresses legitimate
  revisions (#142 was one) and needs a release to reach consumers.
- **Keep "when unsure choose candidate-common".** Rejected: the stated cost
  model ("one extra review") ignored that a mis-tagged skill is re-swept from
  every clone; 4 of the recent unique skill candidates were out of charter.
- **Chosen**: both ends + the tagging rule. Each end is fail-open and
  independently useful.

## Guardrails

- `edit-write-guard` / Art.11.2: all edits in `governance_core/` and
  `maintainer/` sources; autonomy copies refreshed by `upgrade`.
- Security surface: intake still never promotes and never closes; it only adds
  labels and one comment, as today. Workflow permissions unchanged.
- `runtime_import_audit`: no hook gains a `governance_core` import (the changes
  are in a tool, a library module and a maintainer script).
- Art.4: no `.get(k, default)` in new package code.
- Art.8: sweep's hub check runs the same code path in tests (gh subprocess
  mocked at the process boundary) and in production.

## Phases

### Phase 1: Implement both ends + tagging rule

- Deliverables: the changes in Scope; label `revision` created; version 0.43.1.
- Validation: see Validation Plan.
- Exit criteria: all suites green; doctor exit 0; wheel check clean.

## Approval Criteria

- [ ] Field Dictionary: no persisted / cross-agent field added, contracts N/A stated — human-verify: table rows are all in-memory or label-only
- [ ] Every capability / mutation has a named realizer — human-verify: sweep CLI, intake Actions job, extract-skill step named above
- [ ] Open Questions resolved or defaulted — human-verify: both carry a stated default
- [ ] Recovery suite passes incl. new list_hub_candidate_issues cases — cmd: python tools/test_candidate_recovery.py
- [ ] Sweep suite passes incl. non-empty-ledger hub-check case — cmd: python tools/test_candidate_sweep.py
- [ ] Intake suite passes incl. duplicate / dup-of-rejected / revision / fail-open cases — cmd: python maintainer/test_candidate_intake.py
- [ ] Replay: the real 2026-08/09 backlog bodies classify as observed (#143 #145 duplicate of #140; #144 #146 duplicate of #141; #142 revision of #141) — human-verify: replay output recorded in State Log
- [ ] Self-install healthy — cmd: governance-core doctor

## Validation Plan

1. The three script suites above + `pytest tools/` + `maintainer/test_curate_gate.py`.
2. Replay `classify_duplicate` over the saved bodies of #140-#146 in issue order.
3. `governance-core upgrade --project-root .` + `doctor`; `tools/audit_proposals.py`.
4. Wheel content check (top-level `governance_core*` only, no `maintainer/`).
5. Live proof of intake comes with the next real candidate issue; until then the
   `main()` branches are covered with `gh` mocked.

## Rollback / Recovery

Revert the commit. Sweep falls back to empty-ledger-only self-heal; intake to
label-only. No data migration: no stored format changes. The `revision` label can
stay (inert).

## Risks

- **Intake mislabels a non-duplicate** (low): only on a byte-identical digest
  from a lower-numbered issue or an exact registry match; nothing is closed, the
  comment names the original, and removing a label is one click.
- **Hub listing truncated at 200 issues** (medium over time): an old duplicate
  beyond the window is missed and handled as today. Mitigation: registry
  advisories cover promoted / rejected content independent of the window.
- **Extra `gh` call slows wrap-up** (low): only when something is pending;
  degrades to today's behaviour when `gh` is absent or offline.
- **Charter test under-reports a real governance skill** (low): Q1 lists the
  charter areas explicitly; the consumer can still `/submit-candidate` by hand.

## State Log

- 2026-10-09: draft created by core agent (P-0127)
- 2026-10-09: draft → pending (submit for review: pipeline dedup (both ends) + charter test)
- 2026-10-09: pending → approved (user approval 2026-10-09: '按你的建议逐项完成这些工作' -- step 3 of the presented plan (intake digest dedup labels duplicate + points at original; sweep checks hub by digest on every uplink; governance-layer criterion in lesson-classification / extract-skill). Auto-close deliberately left out as beyond the presented plan.)
- 2026-10-09: approved → implemented (replay over real backlog bodies #138-#147: #143 #145 duplicate of #140; #144 #146 duplicate of #141; #142 revision of #141; others new -- matches manual curation. reconcile: STATE.md + docs/core-manual.md + version files touched beyond Scope tokens (manual update is wrap-up step 3); no scope file left untouched)
