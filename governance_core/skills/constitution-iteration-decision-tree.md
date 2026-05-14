---
name: constitution-iteration-decision-tree
description: When proposing or applying any change to project governance (CLAUDE.md, constitution/*, related red lines or ADRs), use this 4-question decision tree to decide which file the change actually belongs in — total.md / agent.md / knowledge/decisions/adr-*.md / .claude/commands/<skill>.md — before editing.
theme: universal
owner: core
tags: [constitution, governance, decision-tree, amendment-workflow]
---

# Constitution Iteration Decision Tree

A short, always-recallable 4-question tree to route any "I want to add
this rule" intent to the correct file. Companion to the
`/iterate-constitution` skill (which executes the workflow); this guide
is the **decision** content that gets injected at SessionStart Tier B
so agents have it on tap without invoking the full skill.

> **Hard rule**: do NOT edit `CLAUDE.md` directly. It's an
> auto-generated artifact (banner declares this). All changes go to the
> source files via `/iterate-constitution` skill.

---

## The four questions

```
Q1. Does this change affect multiple agents?
   ┌─ Yes  → Q2
   └─ No   → constitution/agent.md (this clone only)
              Use R-rule numbering: rules R1- / data D1- / trade T1- /
              research RES1- (start fresh per agent, no cross-agent
              numbering collisions)

Q2. Is it a red line that hooks / pre-commit / cross-agent contracts
   actually depend on?
   ┌─ Yes  → constitution/total.md main article
   └─ No   → Q3

Q3. Is it historical context, a decision rationale, or an experiment
   conclusion?
   ┌─ Yes  → knowledge/decisions/adr-*.md (NOT the constitution)
              The constitution may carry a "see ADR-X" pointer under the
              red line that this ADR motivates, but the substance lives
              in the ADR.
   └─ No   → Q4

Q4. Is it operational steps, a checklist, or a command sequence?
   ┌─ Yes  → .claude/commands/<name>.md (a skill)
              The constitution carries a "calling this skill is a blocking
              rule" pointer ONLY — never the steps themselves
              (Skill Single Source of Truth, total.md 第十三条 附录)
   └─ No   → Re-classify; if none of Q1-Q4 fit, the change probably
             doesn't belong in governance at all
```

---

## Why this tree exists

- **Without Q1**: agents pollute `total.md` with agent-specific rules
  (every clone's CLAUDE.md grows; 2026-04-28 R5 incident — core's
  agent.md held 193 lines of rules R1-R4 by mistake)
- **Without Q2**: red lines that hooks need get hidden in agent.md
  where other agents can't see them
- **Without Q3**: lesson tables clutter the constitution; agents read
  300-line "history" sections every session for content that should be
  in `knowledge/decisions/`
- **Without Q4**: skill steps duplicate into the constitution; the
  constitution drifts when the skill iterates (2026-04-20 wrap-up
  drift — Art.14 said 3 items, skill had 7; agents followed Art.14 and
  missed 4 items per session)

---

## After deciding the file, decide the position

| Action | Where | Bump |
|--------|-------|------|
| Add new article | append after last article, sequential numbering | YES — also update 总宪法 第十三条 红线清单 if it's a red line |
| Add sub-clause | append into existing article's sub-section (X.Y) | NO |
| Modify existing | Edit existing text | commit message must explain backward compat |
| Delete | **Forbidden** — must go through full `proposals/` flow with deprecation period | — |

---

## Common mistakes the tree prevents

- ❌ Putting "rules R1.2 SMIC kline_lookback incident" in total.md (it's
  Q3 → ADR; the red line "kline_lookback >= 200" can stay in
  rules-agent agent.md, but the lesson goes to ADR)
- ❌ Putting "wrap-up has 7 checklist items" in total.md (it's Q4 →
  skill; the constitution says "must invoke /wrap-up", nothing about item count)
- ❌ Putting "trade prefers heredoc commits" in total.md (it's Q1 → No
  → trade's agent.md, not all-agent total)
- ❌ Putting "禁止 .get(key, default)" in agent.md (it's Q2 → Yes →
  total.md red line; hooks across all clones depend on it)

---

## See also

- `.claude/commands/iterate-constitution.md` — the workflow skill that
  executes this decision plus regen/audit/sync
- `constitution/total.md` 第十三条 — modification authority + red lines
  appendix; the "Skill Single Source of Truth" principle is in 第十三条
  附录
- `proposals/iterate_constitution_skill.md` — the proposal that
  introduced this skill + decision tree
