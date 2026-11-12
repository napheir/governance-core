---
id: P-0134
agent: core
status: implemented
created: 2026-11-06
approved_at: 2026-11-06
started_at: 2026-11-06
implemented_in: 9cdc8ef
implemented_at: 2026-11-06
related: [P-0119]
owner: core
---

# Proposal P-0134: Let an approved proposal opt in to Workflow multi-agent execution

## Trigger

Upstream suggestion from deva-vani (2026-11-06), low priority, no deadline. Their owner wants the Claude Code Workflow tool, which runs several subagents in parallel, to be an execution option that the proposal process enables. Approving a proposal that declares Workflow execution counts as the owner's opt-in for the declared scale.

deva-vani already does this locally, without touching gc-managed files. They use a project skill (`.claude/skills/workflow-via-proposal.md`) and a constitution clause (their Art.5.5). They asked gc to provide it, because `/proposal` is gc-managed and they cannot extend it. Our owner asked for this proposal to be drafted (2026-11-06: "起草 Workflow 多 agent 编排提案").

## Current State (read, not assumed)

- **The Workflow tool's opt-in rule** (Claude Code harness). Explicit opt-in is required: the "ultracode" keyword, the user asking in their own words, or "the user invoked a skill or slash command whose instructions tell you to call Workflow". Scale is bounded by the session's *Dynamic workflow size* guideline (default: medium, under 10 agents), which the user can change in `/config`.
- **`execution:` is already taken** by P-0119.
  - Frontmatter schema: `governance_core/contracts/proposal_frontmatter_schema.md:185` says `execution` is a gate runner id; gc ships only `gates`.
  - At approve, `governance_core/tools/proposal_lib.py:1298` runs `gate_calibration_adequacy` whenever `execution` is truthy, which demands `gate:` + `calibration:` on every phase.
  - `run_proposal` (`proposal_lib.py:1107-1135`) executes `cmd:` gates.
  - `contracts/proposal_gate_schema.md:94-97` lists "not a workflow engine" as a non-goal.
  - So `execution: workflow` would trip the calibration gate and the gates runner.
- **No CLI writes `execution:`.** `create_proposal(slug, title, agent)` (`proposal_lib.py:1162`) takes no execution flag, and the subcommands (`proposal_lib.py:2001-2088`) have no setter. Frontmatter must not be hand-edited (`/proposal` anti-patterns).
- **No command appends to the State Log** outside `transition --note` / `link`.
- **Existing approve-time FORM gates and their shared audit checks:**
  - Current State (Check 13);
  - Design & Contract (complex proposals only, Check 14);
  - Approval Criteria tokens (Check 15);
  - execution-class calibration (Check 16).
  - Each BLOCK and its WARN share one predicate.
- **deva-vani's local design.** Read from `deva-vani/agent-core/.claude/skills/workflow-via-proposal.md`.
  - Section: `### 执行方式：工作流` under Design & Contract. Its first line is a token-usage warning, followed by parallelism, scale, cost, write scope, verification, and failure/resume.
  - Approval Criteria gets a `human-verify:` consent item.
  - The approval request repeats the warning.
  - Exceeding the scale or write scope needs a new owner OK.
  - Actual figures are recorded in the State Log afterwards.

## Scope

- `governance_core/contracts/proposal_frontmatter_schema.md` (1.6.0 → 1.7.0): optional field `orchestration`, value `workflow`.
- `governance_core/contracts/proposal_gate_schema.md` (1.0.0 → 1.1.0): the `### Workflow Execution` section grammar, the `workflow_declaration_adequacy` predicate, and the runner's behaviour for orchestrated proposals.
- `governance_core/tools/proposal_lib.py`:
  - `create --orchestration workflow`;
  - `orchestrate --id P-NNNN --set workflow|--clear`, allowed in draft only;
  - the predicate and its approve BLOCK;
  - `run` showing the frozen declaration for an orchestrated proposal;
  - a scaffold hint line.
- `governance_core/tools/audit_proposals.py`: Check 22, a WARN that uses the same predicate for in-flight orchestrated proposals.
- `governance_core/commands/proposal.md`: when to consider workflow execution, how to declare it, what the approval request must say, how execution runs, and what gets recorded afterwards.
- Tests: `governance_core/tools/test_proposal_orchestration.py`.
- Version 0.50.0 (new capability).

## Design & Contract

### Interfaces, I/O & Realization

- **Frontmatter `orchestration: workflow`** (optional). Absent means a normal single-session proposal. It is independent of `execution:`, so a proposal may have both: Workflow does the work, and gates verify the phases.
- **`proposal_lib.py create --orchestration workflow`** writes the field at creation and adds a `### Workflow Execution` skeleton under Design & Contract.
  - **`orchestrate --id P-NNNN --set workflow` / `--clear`** sets or removes it on a draft (status `draft` only), with a State Log line.
  - Realizer: the proposal_lib CLI.
- **`workflow_declaration_adequacy(body) -> (ok, reason)`.** FORM-only. It is the shared predicate behind the approve BLOCK and audit Check 22.
  - INPUT: the proposal body.
  - The section `### Workflow Execution` must exist.
  - Its first non-blank line must start with `> **[TOKEN WARNING]**` and have non-placeholder text after the marker.
  - It must contain these labelled items, each non-empty and non-placeholder: `- Parallelism:`, `- Scale:` (must contain a digit), `- Cost:`, `- Write scope:`, `- Verification:`, `- Failure & resume:`.
  - `## Approval Criteria` must contain at least one `human-verify:` item.
  - OUTPUT: `(True, "")`, or `(False, <first missing item>)`.
- **`transition --to approved`** BLOCKs an orchestrated proposal whose declaration fails the predicate. Exemption `--allow-thin-workflow` (justify in `--note`). The owner's approval words go to the State Log via `--note`, as for every approval.
- **`run --id P-NNNN`** on an approved or in-progress orchestrated proposal prints the frozen declaration (scale, write scope, verification) and exits 0. If the proposal is also execution-class, it then runs the gates as today. It never calls Workflow: the Workflow tool is invoked by the agent, not by a CLI.
- **`/proposal` skill text is the realizer of the actual multi-agent run.**
  1. When an orchestrated proposal is submitted for approval, the agent's approval request must restate, in the message itself, that Workflow will sharply increase token usage, together with the declared scale and cost.
  2. Once the owner approves in their own words, the agent may run it. It loads the `workflow-authoring` skill, then runs within the declared agent count, phases and write scope.
  3. Exceeding any of these needs a new owner OK.
  4. At `complete`, the `--note` records the actual agent count, duration, where the results are, and how they were verified.

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `orchestration` | string | the proposal's work runs as a Workflow (multi-agent) at a declared scale | `create --orchestration` / `orchestrate` | approve gate, audit Check 22, `run`, `/proposal` skill | enum `workflow`; optional; governed by `contracts/proposal_frontmatter_schema.md` (new §4.x, v1.7.0) |
| `### Workflow Execution` section | body section | the declaration the owner approves | drafting agent | `workflow_declaration_adequacy`, approver | grammar in `contracts/proposal_gate_schema.md` (new §, v1.1.0) |
| `[TOKEN WARNING]` line | first line of the section | explicit warning that token usage rises sharply | drafting agent | approver | marker fixed; text in any language; `contracts/proposal_gate_schema.md` |

### Flow

draft (`create --orchestration workflow`, filling the section) → submit: the agent's approval request restates the token warning, scale and cost → approve: the predicate BLOCKs an incomplete declaration, and the owner's words are recorded in the State Log → the owner gives the go → the agent loads `workflow-authoring` and calls Workflow within the declared scale → results are verified as declared → `complete --note` records the actual scale and results → archive.

## Non-Goals

- Running Workflow from a CLI or hook. Only the agent can call the tool.
- Changing gc's clauses or constitution text. A consumer may add a clause like deva-vani's Art.5.5 through its own `/iterate-constitution`.
- Measuring or enforcing actual token spend. The declaration is FORM-checked; staying within scale is the agent's duty under the skill, and the State Log record makes it auditable.
- Surfacing orchestrated proposals in session-context. This can be added later if useful.

## Open Questions

Decided by the owner at approval (2026-11-06, "批准", taking the stated defaults):
- Q1: `orchestration: workflow`.
- Q2: approval is the opt-in; the agent still states once, before starting, what it is about to run.
- Q3: no exemption flag.

- **Q1: field name.** `orchestration: workflow` (recommended: it keeps `execution:` meaning "gate runner", as P-0119 defined it) versus reusing `execution: workflow` (the peer's wording; it would have to fork the calibration gate and the runner by value). Default if undecided: `orchestration`.
- **Q2: is approval itself the opt-in?** Leaning yes: the owner's approval words, given after a request that restated the warning, scale and cost, count as "the user asked in their own words". This matches deva-vani's design. The alternative is to require a separate "go" from the owner at run time. Default if undecided: approval is the opt-in, and the agent still states once, just before starting, that the run is beginning and at what scale.
- **Q3: an exemption flag.** Should `--allow-thin-workflow` exist? deva-vani's owner required the warning, so there is a case for no exemption. Default if undecided: no exemption flag.

## Alternatives & Rationale

- **A. Body section only, no frontmatter field.** The approve gate would trigger on the heading alone. Rejected: the trigger would depend on the section's wording and language, and audit or session tools could not list orchestrated proposals without parsing bodies.
- **B. Reuse `execution: workflow`.** Rejected (see Q1): it overloads the gate-runner field, and it would block a proposal that wants both Workflow execution and phase gates.
- **C. A gc constitution clause plus a skill, as deva-vani did locally.** Not chosen: a clause adds no enforcement, while a predicate does. The skill text in `/proposal` plus the approve gate carry the rule. Consumers stay free to add a clause.
- **Chosen:** a separate optional field, a FORM-checked declaration with a fixed English marker and labels (the scaffold already uses English headings; content may be in any language), and skill text as the realizer.

## Guardrails

- proposal-classify-fast and edit-write-guard cover the `contracts/` and `proposal_lib` edits; all are package source under the normal Art.11 loop.
- command-guard: none of this adds commands.
- sensitive-data-guard: no secrets involved.
- The Workflow tool itself enforces its own opt-in. This proposal only defines when the agent may treat the owner's approval as that opt-in.

## Phases

### Phase 0: Contract

- Deliverables:
  - `proposal_frontmatter_schema.md` 1.7.0 (`orchestration`);
  - `proposal_gate_schema.md` 1.1.0 (the Workflow Execution grammar, the predicate and runner behaviour);
  - before bumping, `git grep` both target version numbers to make sure no document reserves them.
- Validation: the contract text matches the Design & Contract above.
- Exit criteria: both contracts are updated and the Q1–Q3 decisions are applied.

### Phase 1: proposal_lib, audit and skill

- Deliverables:
  - the create flag, the `orchestrate` subcommand, the predicate and approve BLOCK, `run` showing the declaration, the scaffold hint, audit Check 22;
  - a `/proposal` skill section;
  - tests;
  - version 0.50.0.
- Validation:
  - the new tests pass, and calibration against HEAD fails on the new behaviour;
  - the full suite passes;
  - upgrade shows no drift and doctor exits 0.
- Exit criteria: committed and released after the owner confirms. deva-vani is told it can drop its local skill.

## Approval Criteria

- [ ] An orchestrated proposal without a complete declaration cannot be approved; one with it can — cmd: python -m pytest tools/test_proposal_orchestration.py -q -p no:cacheprovider
- [ ] Audit Check 22 and the approve gate share one predicate — cmd: python -m pytest tools/test_proposal_orchestration.py -q -p no:cacheprovider -k audit
- [ ] `execution:` proposals behave exactly as before — cmd: python -m pytest tools/test_proposal_gates.py -q -p no:cacheprovider
- [ ] The `/proposal` skill tells the agent to restate the token warning, scale and cost in the approval request, and to stop and ask before exceeding the declared scale or write scope — agent-rubric: governance_core/commands/proposal.md workflow section covers restate-on-request, stay-within-scale, record-at-complete
- [ ] Q1–Q3 are decided by the owner — human-verify: owner states the choice for each

## Validation Plan

- Unit tests for the predicate: missing section, missing warning, warning not on the first line, each missing label, a scale without a digit, no `human-verify:` criterion, and a complete declaration.
- A transition test: approve is blocked or allowed, and the exemption (if Q3 keeps it) is honoured.
- An audit test: Check 22 WARNs on the same failing body.
- A `run` test: the declaration is printed; when the proposal is also execution-class, the gates still run.
- Regression: the P-0119 gate tests are unchanged.
- Calibration: the new tests run against HEAD fail.

## Rollback / Recovery

The field is optional and additive. Reverting the commit removes the gate. Proposals already carrying `orchestration:` then simply have an unused field; the audit ignores unknown fields, so nothing breaks.

## Risks

- **Medium: the harness reads the opt-in differently** (Q2), and treats approval as insufficient. Mitigation: the agent says once, before starting, what it is about to run. If the harness asks for confirmation, the owner gives it.
- **Low: declared scale exceeds the session's Dynamic workflow size.** The skill tells the agent to note the guideline in the declaration. The owner can raise the guideline in `/config`.
- **Low: label wording.** Labels are English. Consumers who write Chinese content still use the English labels, as they already do for the scaffold headings.

## State Log

- 2026-11-06: draft created by core agent (P-0134)
- 2026-11-06: linked related P-0119
- 2026-11-06: draft → pending (submit for review)
- 2026-11-06: pending → approved (owner: 批准 (2026-11-06); Q1-Q3 per the stated defaults: orchestration field, approval is the opt-in, no exemption flag)
- 2026-11-06: approved → in-progress
- 2026-11-06: in-progress → implemented (reconcile: scope fully touched; extras STATE/version files/core-manual only; release 0.50.0 pending owner)
