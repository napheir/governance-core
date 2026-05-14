---
theme: universal
name: proposal-vs-plan-mode-vs-commit
description: Decide whether a change needs a proposals/*.md file, plan mode deliberation, or just a commit. Default heuristic — if you can write AND commit it in this session within your own scope, skip the proposal. Proposals are cross-actor authorization tokens, not general planning artifacts. Misuse creates "ceremonial proposals" that the author writes, reviews, and executes alone — pure overhead.
type: guide
tags: [governance, process, proposals, plan-mode, meta]
created: 2026-04-24
updated: 2026-04-24
---

# Proposal vs Plan Mode vs Commit

Before writing `proposals/<something>.md`, check which mechanism actually fits the work. All three exist for different problems; using the wrong one wastes effort or weakens audit trails.

## Three mechanisms

| Mechanism | What it solves | Persistence | Who authorizes | Who executes |
|-----------|----------------|-------------|----------------|--------------|
| **Plan mode** | "Think before acting; get user to approve deliberation" | Session-scoped (vanishes on /compact / exit) | User clicks once | Same agent, same session |
| **`proposals/*.md` file** | "Hand a task across scope or time boundaries" | Git-tracked; survives sessions and clone switches | Human / core agent review | A different agent (or future you) |
| **Direct commit** | "Do the work; the diff + commit message is the audit trail" | Git-tracked via history | Nobody (agent is in scope) | This agent, now |

## Decision flow

Ask in order; stop at the first yes.

1. **Can you physically execute this within your own clone's scope RIGHT NOW?**
   → Direct commit. The diff + commit message is sufficient audit trail.
   (Plan mode optional if you want a safety checkpoint before a big edit.)

2. **Do you need to pause now and hand this off to another actor?** Typical cases:
   - Cross-scope: file lives outside your `agent_rules/*.allow.txt`
   - Cross-clone: file physically lives in another clone's worktree
   - Constitutional: touches `contracts/`, `agent_rules/`, `CLAUDE.md`, or generator sources
   - Architectural: want a durable ADR-like record for future readers
   - Asynchronous review: a human needs to look at this before execution
   → `proposals/<name>.md`. Commit it under your own scope. Another agent picks it up.

3. **Is this complex enough you want to sketch intent before editing, but you'll execute it yourself this session?**
   → Plan mode. It locks tools until approval, then you execute.
   Don't materialize the plan as a `proposals/*.md` file — the plan output vanishes with the session, which is fine because the commit will preserve the outcome.

## Anti-patterns

### The ceremonial proposal

> Agent writes `proposals/refactor-foo.md`, reviews it themselves in the same session, then writes and commits the refactor in their own scope.

This is pure overhead. The `proposals/` directory is meant to carry context across an actor or time boundary. When the author, reviewer, and executor are the same agent in the same session, there's no boundary to cross — just commit the work with a good message. The commit message carries the same "why" the proposal would have.

**Test:** if you can answer yes to "will I open and edit this file again, or will only my commit touch it?", it's ceremonial. Delete the draft, commit the work.

### The plan-mode-as-proposal confusion

> "I'll use plan mode to write up the design, then the user can review it, then I'll execute."

Plan mode's approval gate is single-turn. It's not a durable review artifact. If you want the design preserved, either put it in the commit message or, if it's substantial, write an ADR to `knowledge/decisions/`. If you need someone ELSE to review before you execute, proposals/ is the right path.

### The proposal as task tracker

> Agent writes `proposals/phase-3-migration.md` to keep themselves organized across sessions.

That's what `TaskCreate` / `STATE.md` / in-conversation notes are for. Proposals are scoped to cross-actor authorization, not personal task tracking.

## What good proposal scope looks like

A proposal earns its weight when at least one of these is true:

- **Cross-scope write**: "core needs to modify `agent_rules/rules.allow.txt`"
- **Cross-clone operation**: "rules asks core to run `sync_infra.py --execute` from agent-core clone"
- **Breaking change**: "generator v2 changes feature column semantics; list migration steps"
- **ADR candidate**: "picked strategy A over B because X; future readers will ask why"
- **Multi-session**: "the migration takes 3 weeks; handoff doc for whoever's on this next"

If none of these apply, the proposal is probably ceremonial.

## Cross-reference

- This skill was distilled from a 2026-04-24 conversation where the user asked *"if within own agent scope you directly discuss a proposal, what's the difference from plan mode?"* — the answer is: often none, and that's a signal the proposal is redundant.
- Governance source: Constitution 第五条 (proposal mechanism) + 第十二条 (scope execution).
