# Contract: Proposal Gate & Check Grammar

**Version**: 1.1.0
**Status**: active
**Owner**: core
**Consumers**: all agents (write Approval Criteria + execution-class phase gates
+ Workflow Execution declarations), `tools/proposal_lib.py`
(`approval_criteria_adequacy`, `gate_calibration_adequacy`,
`workflow_declaration_adequacy`, `run`), `tools/audit_proposals.py` (Checks 15,
16, 22), `.claude/commands/proposal.md` (skill).

Defines the small, runner-agnostic grammar that makes a proposal's acceptance
signals **decidable** (P-0119). Builds on the two existing approve-time
form-gates (Current State — P-0108, Design & Contract — P-0124): like them these
are **FORM-only** machine checks — they verify a discriminating check is
*present*, never that it *passes* (that stays the approver's / runner's call).

---

## 1. Check-token grammar (universal — every Approval Criteria item)

Every `## Approval Criteria` checklist item pairs a plain-language **acceptance**
with exactly **one** discriminating **check token**:

```markdown
- [ ] <acceptance: what "done" means, in plain words> — <check-token>
```

| Check token | Meaning | Decided by |
|-------------|---------|------------|
| `cmd: <shell command>` | Passes iff the command exits 0. | machine (runner / CI / human runs it) |
| `agent-rubric: <ref>` | An agent judges the artifact against a named rubric (`ref` = a path or one-line rubric). | agent |
| `human-verify: <sentence>` | A human confirms the stated condition. | human |

- **Exactly one** token per item. An item with no token is prose, not an
  acceptance signal — the drafting scaffold shows the grammar and
  `approval_criteria_adequacy` FORM-checks that each item carries a token.
- FORM-only: the gate checks the token is *present*, not that `cmd:` exits 0.
- The token is the last `—`/`--`-separated clause of the item line (or a
  continuation line beginning with the token prefix).

## 2. Execution-class phase gates (opt-in — `execution:` frontmatter present)

A proposal whose frontmatter carries `execution: <runner>` (gc ships `gates`) is
**execution-class**: its `### Phase` entries are machine-run. Each real (non-
placeholder) phase then carries a signed **gate** + a **calibration** line:

```markdown
### Phase 1: <title>

- Deliverables: ...
- gate: cmd: python -m pytest tools/test_x.py
- calibration: neg tests/fixtures/broken_x → FAIL; golden tests/fixtures/good_x → PASS
- Exit criteria: ...
```

- `gate:` uses the §1 check-token grammar (`cmd:` / `agent-rubric:` /
  `human-verify:`).
- `calibration:` evidences that the gate **discriminates**: a negative fixture
  the gate must FAIL on, and a golden fixture it must PASS on. A check that
  passes on a broken input is not a gate.
- `gate_calibration_adequacy` FORM-checks that each real phase of an
  execution-class proposal has both a `gate:` and a `calibration:` naming a
  `neg ... → FAIL` and a `golden ... → PASS`. FORM-only — it does not run them.

## 3. Runner (`/proposal run <id>`)

For an approved or in-progress **orchestrated** proposal (§5), `run` first
prints the frozen Workflow Execution declaration and exits 0. It never calls
the Workflow tool, which only the agent can invoke. If the proposal is also
execution-class, the gates below then run as usual.

`/proposal run <id>` → `proposal_lib.py run --id P-NNNN` executes an
**approved** (or in-progress) **execution-class** proposal's per-phase `gate:`
tokens:

- Only `cmd:` gates auto-run (exit 0 = pass); `agent-rubric:` / `human-verify:`
  gates are reported for manual sign-off.
- Refuses (non-zero) when the proposal is not approved/in-progress, or not
  execution-class. Approval **freezes** the gate set: editing an approved gate
  requires re-approval (zero-tolerance drift), so "approved proposal → runnable
  gates" has one source of truth — the proposal body, not a separate run-spec.
- **Security**: a `cmd:` gate is an arbitrary command. Approving an
  execution-class proposal is the human's authorization of its gate commands;
  `run` executes them synchronously in the repo root. Gate commands are subject
  to the same `command-guard` denylist as any other command.

## 4. Enforcement & audit (form-only, shared predicates)

| Predicate (`proposal_lib.py`) | approve BLOCK | audit WARN |
|-------------------------------|---------------|------------|
| `approval_criteria_adequacy(body)` | every criteria item has a check token (transitional: WARN, then BLOCK — P-0119 Phase 3) | Check 15-criteria (in-flight) |
| `gate_calibration_adequacy(body)` | execution-class only: every real phase has `gate:` + `calibration:` | Check 15-calibration (in-flight execution-class) |
| `workflow_declaration_adequacy(body)` | orchestrated only (`orchestration: workflow`): a complete §5 declaration; **no exemption** | Check 22 (in-flight orchestrated) |

Each BLOCK and its audit WARN share the **same predicate** so the two can never
disagree (mirrors Current State / Design & Contract Checks 13 / 14). Exemptions
`--allow-unsigned-criteria` / `--allow-uncalibrated-gate` (justify in `--note`).
Proposals created before the cutover date are grandfathered (the gate grammar
did not exist).

## 5. Workflow Execution declaration (opt-in — `orchestration: workflow`)

A proposal whose frontmatter carries `orchestration: workflow` (frontmatter
schema §4.8) runs its work as a Claude Code **Workflow**: several subagents in
parallel. The owner's approval of the proposal is the opt-in for the scale it
declares. Because a Workflow multiplies token use, the declaration must make
that cost explicit before anyone approves it.

The declaration is an H3 section, normally placed under `## Design & Contract`:

```markdown
### Workflow Execution

> **[TOKEN WARNING]** Running this as a Workflow sharply increases token usage: about <N> agents, roughly <X>x a single session doing the same work.

- Parallelism: <which sub-tasks run in parallel and why they are independent>
- Scale: <phases, agents per phase, total; how it relates to the session's Dynamic workflow size>
- Cost: <rough token and time estimate>
- Write scope: <read-only reports (recommended), or the exact paths agents may write, within the initiating agent's scope>
- Verification: <how results are checked before anything acts on them>
- Failure & resume: <what happens on a failed or interrupted run, e.g. resumeFromRunId or a narrower re-run>
```

`workflow_declaration_adequacy(body)` FORM-checks:

- the `### Workflow Execution` section exists;
- its first non-blank line starts with `> **[TOKEN WARNING]**`, with
  non-placeholder text after the marker;
- each labelled item (`Parallelism`, `Scale`, `Cost`, `Write scope`,
  `Verification`, `Failure & resume`) is present and non-placeholder (not
  empty, not `<...>`, not `TBD`), and `Scale` contains a digit;
- `## Approval Criteria` has a `human-verify:` item whose line names the
  Workflow (contains `workflow`, any case): the owner's consent to Workflow
  execution at the declared scale. The scaffold's generic `human-verify:`
  items do not count.

The marker and labels are fixed English strings, like the scaffold's headings;
the text after them may be in any language. FORM-only: the check does not judge
whether the scale or cost is right. That stays the approver's call.

**Agent duties** (in `/proposal`, not machine-checked):

- When an orchestrated proposal goes for approval, the agent restates in the
  request message itself that the Workflow sharply increases token usage, with
  the declared scale and cost.
- After approval, the agent says once, before starting, what it is about to run
  and at what scale. It loads the `workflow-authoring` skill and stays within
  the declared agents, phases and write scope. Exceeding any of them needs a new
  owner OK.
- At `complete`, the `--note` records the actual agent count, duration, where
  the results are, and how they were verified.

## 6. Non-goals

- Not a workflow engine: the gate runner has no DAG / parallelism / retry — it
  runs a phase's `cmd:` gates in order. A Workflow run (§5) is started by the
  agent, never by `proposal_lib`.
- Does not judge substance: FORM-only, consistent with the two existing gates.
- Does not meter or cap actual token spend; the §5 declaration plus the
  `complete` record make it auditable.
- No consumer `todo`↔proposal linkage (a consumer-local business bridge; gc
  ships no todo system).

## 7. Versioning

- **1.1.0** (2026-11-06, P-0134): §5 Workflow Execution declaration,
  `workflow_declaration_adequacy`, audit Check 22, runner prints the declaration.

SemVer. Minor = new token kind / new optional gate line (backward compatible);
major = removed/renamed token or breaking grammar change (needs a `proposals/`
entry + staged migration).
