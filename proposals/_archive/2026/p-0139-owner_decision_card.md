---
id: P-0139
agent: core
status: implemented
created: 2026-11-17
approved_at: 2026-11-17
started_at: 2026-11-17
implemented_in: d9e4256
implemented_at: 2026-11-19
owner: core
---

# Proposal P-0139: Ship the owner decision card as a gc capability

## Decision Card

- 改动：gc 自带决策卡 skill；每次提问的宪法提醒加一句；提案模板加"决策卡"一节，submit/approve 缺卡只警告；/upgrade 确认和发布确认用卡。
- 代价：一个阶段实现，发 0.53.0；每条消息多约 25 个 token。
- 风险：小事也出卡变噪音（skill 写明只在需要 owner 决定时用）。
- 撤销：回退发布；已有"决策卡"一节的提案照样有效。
- 你怎么察觉：升级后 deva-vani 的会话不用交代就出卡。
- 替你选的默认：始终开启、无配置项；只警告不拦截；加每次提醒；先发 0.52.1。

## Trigger

- **Owner (2026-11-17):** "我认为决策卡是一个不错的公共能力，希望让GC支持。" (The decision card is a good common capability; gc should support it.)
- **Background.**
  - On 2026-11-12 the owner reported losing track of details and earlier decisions under parallel, long-running work.
  - They adopted two habits for this session: a decision card in front of every approval request, and a "waiting on you" (等你处理) list at the end of messages. They called the P-0136 card "很有用" (very useful).
- **The gap.** Both habits live only in the hub's auto-memory, which is per project. The owner saw no cards in deva-vani, whose four clones are four separate projects.
- **Why gc.** Shipping it reaches every gc project, including projects later handed over to colleagues, without each owner configuring anything.

## Current State (read, not assumed)

- **No gc file mentions the card.** A search of `governance_core/` for "decision card", "决策卡", "waiting on you" and "等你处理" finds nothing.
- **Per-prompt reminder.** `governance_core/hooks/constitution-reminder.py:22-26` prints one line on every prompt, covering Art.0 (ritual) and Art.14 (wrap-up) only.
- **Skill menu is capped.**
  - `governance_core/discovery/registry.py:437` `_UNIVERSAL_INJECTION_LIMIT = 10`.
  - `emit_bounded_injection` sorts by usage score, then name (`registry.py:481`), prints the first 10 (`:507`), and folds the rest into "+N more" (`:512`).
  - The hub's SessionStart today shows 10 universal skills and "+12 more". A new, unused universal skill would sit in the hidden tail.
- **Shipped guides.** `governance_core/skills/*.md` carry `theme: universal` frontmatter (for example `lesson-classification.md:1-9`). `upgrade` installs them into every clone's `.claude/skills/`.
- **Where agents ask the owner to decide.**
  - `/proposal` (`governance_core/commands/proposal.md:150` submit, `:156` approve; approve needs an explicit owner signal).
  - `/upgrade` step 4, "owner 确认门（阻塞）" (`governance_core/commands/upgrade.md:69`).
  - Releases, which need human confirmation in the hub (core-A3).
- **Proposal scaffold and gates.**
  - `governance_core/tools/proposal_lib.py:604` onward is the scaffold, starting at `## Trigger`.
  - The approve gates are at `proposal_lib.py:1480-1530`. The P-0119 criteria gate (`:1510-1520`) is the precedent for a form-only WARN printed to stderr.
  - The gate grammar contract is `governance_core/contracts/proposal_gate_schema.md` v1.1.0.

## Scope

- New guide `governance_core/skills/owner-decision-card.md` (`theme: universal`): the one place that defines the card and the waiting list.
- `governance_core/hooks/constitution-reminder.py`: one more short sentence pointing to the card.
- `governance_core/tools/proposal_lib.py`:
  - the scaffold gains `## Decision Card` right after the title;
  - a form-only WARN on `submit` and `approve` when the card is missing, still the placeholder, or longer than 8 lines.
- `governance_core/commands/proposal.md` (submit, approve), `governance_core/commands/upgrade.md` (step 4): point to the guide.
- `docs/core-manual.md`: release confirmation uses the card; a short section on the capability.
- `governance_core/contracts/proposal_gate_schema.md`: the card WARN, 1.2.0.
- Tests: `governance_core/tools/test_decision_card.py` (new).
- Version 0.53.0.

## Design & Contract

### Interfaces, I/O & Realization

- **Guide `owner-decision-card`** (static file, read by the agent).
  - Content:
    - **When:** any request for the owner's decision: a proposal approve or reject, a release, an upgrade confirmation, a choice between options.
    - **The card:** at most 8 lines, in the owner's language. It covers what changes, the cost, the risk, how to undo it, how the owner would notice a problem, and which defaults the agent picked on the owner's behalf.
    - **The waiting list:** end every message that leaves something open with a short list of what waits on the owner.
    - **Delegated defaults:** when the owner says "as you suggest", write down which defaults were delegated (for a proposal, in the approve `--note`).
  - Realizer: the agent, prompted by the reminder line and the `/proposal` and `/upgrade` steps.
- **constitution-reminder.py** (UserPromptSubmit, prints to stdout).
  - Output: the existing line plus "When asking the owner to decide: decision card first (skill owner-decision-card); end with what waits on the owner."
  - Realizer: Claude Code runs the hook on every prompt.
- **proposal_lib** (CLI).
  - `create` writes a `## Decision Card` section holding a placeholder.
  - `transition --to pending` and `--to approved` call `decision_card_adequacy(body) -> (ok, reason)`. When it fails, they print `[WARN] P-NNNN: decision-card gate -- <reason>` to stderr and continue. `--allow-no-card` silences it.
  - The check passes when the section exists, is not the placeholder, and has 1 to 8 non-empty lines, not counting `>` guidance lines.
  - Realizer: proposal_lib in the clone's `tools/`.
- **Commands** (static files): `/proposal` submit says "show the owner the card"; approve says "record delegated defaults in --note". `/upgrade` step 4 says "present a card".

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| `## Decision Card` section | markdown, 1-8 lines | the owner-facing summary of the proposal | the drafting agent | owner; `decision_card_adequacy` | form only, substance is the owner's call; contracts/proposal_gate_schema.md (1.2.0) |
| `--allow-no-card` | CLI flag | silence the card WARN | agent | proposal_lib | justify in `--note`; contracts/proposal_gate_schema.md |
| reminder line | stdout text | per-prompt pointer to the guide | constitution-reminder.py | the agent | N/A for contracts: hook output text, not persisted |

### Flow

```
owner prompt -> constitution-reminder (card pointer, every prompt)
agent drafts a proposal -> scaffold has ## Decision Card -> agent fills <= 8 lines
/proposal submit -> decision_card_adequacy -> WARN if missing / placeholder / > 8 lines
agent message to owner -> card first ... waiting-on-you list last
owner approves ("as you suggest") -> approve --note records the delegated defaults
```

## Non-Goals

- **Checking cards in chat.** No hook can verify an agent's prose. The WARN covers only the proposal section.
- **Blocking.** The card gate stays a WARN (see Open Questions 2).
- **The owner desk** (board, decision ledger, weekly digest). It has its own proposal, still to be drafted.
- **The user-level `~/.claude/CLAUDE.md`.** That stays the owner's personal choice. The staged text in `artifacts/owner_prefs/user_claude_md.md` remains available for non-gc projects.
- **Retrofitting the card into archived or in-flight proposals.**

## Open Questions

1. **Always on, or a config switch?** Leaning: always on, with no config key.
   - Art.4 forbids defaulted config reads, so a new required key would break every existing config.
   - The card costs little for an owner who does not want it.
2. **WARN or BLOCK on submit and approve?** Leaning: WARN, then review after a month of use. BLOCK would fail old drafts, and the substance is the owner's call anyway.
3. **The per-prompt reminder line.** Leaning: yes. The SessionStart menu shows only the top 10 universal skills by usage, so a new guide would not be seen. The line costs about 25 tokens per prompt.
4. **Release order.** Leaning: release 0.52.1 (P-0138) first, since its field check is waiting, and ship this as 0.53.0.

## Alternatives & Rationale

- **A. Guide + reminder line + proposal section and WARN (chosen).** One definition (the guide), recall on every prompt (the line), and a concrete slot where most approvals happen (proposals). Every piece fails soft.
- **B. A constitution clause.** It is the strongest form, but every consumer's own constitution would have to be iterated to cite it, and a clause binds a communication habit as law. Rejected as heavier than the need.
- **C. Guide only.** The cheapest option, but it would sit in the hidden "+N more" tail of the skill menu, so agents would rarely see it. That repeats today's gap.
- **D. User-level `~/.claude/CLAUDE.md` only.** It works at once on this machine, but it does not reach colleagues' machines or projects handed over. Kept as a personal option (Non-Goals).

## Guardrails

- **constitution-reminder** stays informational (exit 0, never blocks); only its text changes.
- **proposal_lib:** the new check is a WARN that never raises, so no transition can fail on it.
- **edit-write-guard / scope-guard / command-guard / boundary-guard:** not affected.
- **Package isolation:** the new guide is a `.md` under `governance_core/skills/`. Check that the existing package-data glob covers it, and confirm in the wheel.

## Phases

### Phase 1: Guide, reminder and proposal slot

- Deliverables:
  - `skills/owner-decision-card.md`;
  - the reminder line;
  - the scaffold section, `decision_card_adequacy`, the WARN on submit and approve, `--allow-no-card`;
  - pointers in `/proposal` and `/upgrade`;
  - core-manual, contract 1.2.0, version 0.53.0;
  - tests: scaffold has the section; placeholder, empty and 9-line cards WARN; a 6-line card passes; the WARN never blocks; the guide is `theme: universal`; the reminder names the guide.
- Validation: full suite; command-guard suite; upgrade; doctor; `audit_knowledge` (theme check); wheel contains the guide.
- Exit criteria: committed; /wrap-up.

### Phase 2: Release and use

- Deliverables: with owner confirmation, release. Ask deva-vani to upgrade.
- Validation: the owner sees cards from a deva-vani session without having told that session.
- Exit criteria: owner confirms. Then complete and archive.

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: each row cites contracts/proposal_gate_schema.md or says N/A with a reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: guide, reminder, gate and command pointers each name what delivers them
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: the owner has ruled on OQ1-OQ4
- [ ] The scaffold, the WARN and the reminder behave as specified — cmd: python -m pytest tools/test_decision_card.py -q
- [ ] No regressions — cmd: python -m pytest tools/ maintainer/ -q
- [ ] The owner sees cards from a consumer project without configuring it — human-verify: owner confirms a card from a deva-vani session after the upgrade

## Validation Plan

- Unit tests (Phase 1 list), run from the root `tools/`.
- Dogfood: the hub's next proposal is drafted from the new scaffold.
- Field: the owner's check in deva-vani (Phase 2).

## Rollback / Recovery

- Revert the release commit. The guide is removed by upgrade's prune, the reminder line goes back, and the scaffold loses the section.
- Proposals already drafted with a `## Decision Card` section stay valid: older proposal_lib ignores unknown sections.

## Risks

- **Card fatigue** (medium). Cards on trivial asks become noise. Mitigation: the guide says one card per decision, and none for status updates.
- **A wrong default buried in the card** (low). The "defaults picked for you" line exists to surface it, and the approve note records it.
- **Per-prompt cost** (low). About 25 tokens per prompt.

## As-built notes

**Phase 1 (2026-11-17)**
- **Guide.** `governance_core/skills/owner-decision-card.md`, `theme: universal`. It covers when to use the card, its six parts, the waiting list, recording delegated defaults, and anti-patterns.
- **Reminder.** `constitution-reminder.py` now ends with "When asking the owner to decide: decision card first (skill owner-decision-card); end with what waits on the owner." No test asserted the old exact text.
- **proposal_lib.**
  - The scaffold opens with `## Decision Card`: a `>` guidance block plus the `<decision card>` placeholder.
  - `decision_card_adequacy` checks that the section exists, is not only the placeholder, and has 1 to 8 lines, with blank and `>` lines not counted.
  - The WARN on `pending`/`approved` goes to stderr through `sys.stderr.write`; `--allow-no-card` silences it.
  - It runs before the approve gates, so a blocked approve still shows the card WARN first.
- **Commands.**
  - `/proposal`: the section order, the submit paragraph, and the approve note on delegated defaults.
  - `/upgrade` step 4: present a card.
- **Docs.** core-manual §6 (release confirmation) and the new §17. Contract `proposal_gate_schema.md` 1.2.0.
- **Dogfood.** This proposal gained its own `## Decision Card` (the card the owner approved).
- **Validation.**
  - `test_decision_card.py`: 11 tests.
  - Full suite: 569 passed. command-guard: 42/42.
  - doctor OK. `audit_knowledge` healthy, after rebuilding the gitignored `knowledge/skills/INDEX.md`.
  - Wheel 0.53.0: the guide and test are in it; only `governance_core*`.

**Phase 2 field report (2026-11-19)**
- deva-vani upgraded to 0.53.0. Their core session (agent-core-75) relayed the owner's feedback, given in that core session: the decision card format is "好用".
- A relayed message is not the owner's confirmation here. The Phase 2 exit criterion waits for the owner to confirm in this session.
- Dogfood: P-0140 was drafted from the new scaffold with a filled card. `submit` gave no card WARN.
- **Owner confirmed in this session (2026-11-19): "好用".** The exit criterion is met.
- Reconcile at d9e4256: every scope file was touched; the extra files are only the version bump (`pyproject.toml`, `__init__.py`) and STATE.md.

## State Log

- 2026-11-17: draft created by core agent (P-0139)
- 2026-11-17: draft → pending (submit for review) by core
- 2026-11-17: pending → approved (owner: 批准 (decision-card defaults: OQ1 always on, no config key; OQ2 WARN not BLOCK; OQ3 add the per-prompt reminder line; OQ4 0.52.1 first, this ships as 0.53.0)) by core
- 2026-11-17: approved → in-progress (start Phase 1 (guide, reminder and proposal slot)) by core
- 2026-11-19: in-progress → implemented by core
