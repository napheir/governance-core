---
theme: universal
name: lesson-classification
description: Decision flow for routing a session-learned lesson to the right store (memory, skill guide, learned skill, CLAUDE.md, knowledge/, or discard). Apply whenever /wrap-up or /learn surfaces a lesson worth capturing — memory alone is passive and rarely fires for design principles.
type: guide
tags: [governance, memory, skills, knowledge, process, meta]
created: 2026-04-17
updated: 2026-04-17
---

# Lesson Classification

> **Example content note**: Examples below reference the upstream project where governance-core was first developed. The skill pattern itself is generic; substitute your own domain examples.


Use this guide whenever a session yields a lesson worth capturing — typically during `/wrap-up` step 4 or `/learn`. The goal is to pick the **one** storage target that makes the lesson reappear in the right future context.

## Why routing matters

| Store | Loading model | Best for |
|-------|---------------|----------|
| Memory (`MEMORY.md` + files) | Passive: index always in context, detail read on relevance hook | Facts about the user, project state snapshots, quiet corrections |
| Skill — guide (`.claude/skills/<name>.md`) | Active: Registry L0 scan ranks by description match | Cross-agent design principles, reusable conventions |
| Skill — learned (`.claude/skills/learned/<name>.md`) | Active: Registry + tracker scoring | Workflows extracted from a specific session; session-boosted recency |
| Command (`.claude/commands/<name>.md`) | Explicit: user types `/name` | User-facing entry points |
| CLAUDE.md / sub-constitution | Forced: always in context window | Inviolable project rules |
| `knowledge/` | Retrieved: searched when relevant questions arise | Decision rationale, experiment results, domain facts |
| Discard | — | Bug fix already captured by diff + commit message |

**Passive stores fail for actionable principles.** A 100-char hook in `MEMORY.md` rarely matches when the next occurrence of the principle looks different on the surface. Active stores (guide/learned) put a description next to its trigger keywords, so Registry L0 matching can surface them.

## Decision flow

Ask in order — stop at the first yes.

1. **Is this a user-specific fact, preference, or slow-moving project state?**
   → Memory (`user` / `feedback` / `project` / `reference`).
   Examples: user is a quant trader, merge freeze ends 2026-03-05, Linear project "INGEST" tracks pipeline bugs.

2. **Is this session-only — a temporary constraint that won't apply next time?**
   → Keep in conversation. Don't persist.
   Examples: "don't refactor the Futu wrapper while I'm mid-migration", "ignore the failing test in PR #42 until tomorrow".

3. **Is this a principle or workflow that should be actively applied when a specific pattern reappears?**
   Ask: can I describe the trigger pattern in one sentence?
   - **Cross-agent** design principle, convention, or reusable pattern → **Skill guide** (`.claude/skills/<name>.md`, type `guide`), discoverable via Registry scan.
   - **Workflow extracted from this session**, likely to replay → **Learned skill** (`.claude/skills/learned/<name>.md`, type `learned`, via `/extract-skill`). Lives in the invoking agent's repo; tracker scoring boosts recency.

   > **Archival destination by topology (P-0068)** — the *classification* above
   > is topology-independent; the physical write location is not. In a
   > self-hosted package project (e.g. governance-core, where `.claude/skills/`
   > is a derived install copy), author a **Skill guide** in the **package
   > source** (`governance_core/skills/<name>.md`) — it installs to
   > `.claude/skills/` via `governance-core upgrade`. **Learned skills** stay
   > in `.claude/skills/learned/`, kept durable there by a `.gitignore`
   > carve-out. The classification decision itself never changes.

4. **Is this a project-wide rule that must never be violated?**
   → CLAUDE.md article. Requires proposal + review (see constitution 第十三条). Do not route here casually — constitutional edits have weight.

5. **Is this decision rationale, experimental result, or domain insight?**
   → `knowledge/<subdomain>/<name>.md` under the relevant agent's knowledge tree.
   Examples: why we picked XGBoost over LightGBM, empirical thresholds from a backtest, domain facts about Futu's K-line alignment.

6. **Otherwise**: discard. Bug fixes are captured by the diff and commit message. Premature capture clutters future search.

## Key test

> Will the agent need to **actively recall and apply** this when doing *different-looking* work in the future, and can I **name the trigger pattern**?

- **Yes + describable trigger** → skill (guide or learned). The description must carry the trigger keywords so Registry L0 matches.
- **Yes + no clear trigger** → memory. Accept that recall is weak; at least the hook is visible in MEMORY.md.
- **No, permanent rule** → CLAUDE.md.
- **No, reference fact** → knowledge/ or memory (reference type).
- **No, already captured by code** → discard.

## Writing the description

For skills, the frontmatter `description:` is the only thing L0 shows. It must:
- Name the trigger pattern first ("When designing X…", "When reviewing Y…")
- Include keywords a future agent will think of when hitting the pattern
- Stay ≤ 200 chars — longer gets truncated in registry tables

Bad: `"Design pattern for infrastructure."` (no trigger, no keywords)
Good: `"When building multi-agent Python infra where code lives in one repo but runs in others, separate code location from state location — use PYTHONPATH for code, invoker-local state paths."`

## Common mistakes

- **Storing a design principle as feedback memory** — hook text can't fire on differently-worded new occurrences. Upgrade to a guide.
- **Storing a per-session workflow as a guide** — clutters Registry for every agent forever. Put it in learned.
- **Routing a constitutional rule to a skill** — skills can be edited freely; CLAUDE.md has change protocol.
- **Writing vague skill descriptions** — `"project convention"` won't match any L0 search. Lead with the trigger pattern.
- **Double-storing** — pick one home. If cross-referencing is essential, keep the full content in the active store (skill) and leave only a one-line pointer in memory.

## Related

- `.claude/commands/wrap-up.md` step 4 — when to invoke this flow
- `.claude/commands/extract-skill.md` — extractor CLI for learned skills
- CLAUDE.md 第十三条 — constitutional edit protocol
- CLAUDE.md 第十六条 — memory freshness policy
