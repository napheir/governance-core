---
theme: universal
name: session-start-git-hygiene
description: On every Claude Code session start, check git status and unpushed commits before starting new work. The SessionStart hook prints a summary automatically — this guide explains what to do about it. Prevents committed-but-unpushed history from piling up across sessions and surfaces stale working-tree drift.
type: guide
tags: [governance, git, session-lifecycle, discipline, cross-agent]
created: 2026-04-17
updated: 2026-04-17
---

# session-start-git-hygiene

## When to apply

- Every session start (SessionStart hook auto-prints the summary — this guide explains the response)
- Diagnosing "someone lost work" / "origin doesn't have X" / "I thought I pushed that"
- Before starting any non-trivial work in a clone that's been idle for a while

## The rule

**At session start, verify local repo state before starting new work.** The `session-context.py` hook automatically prints a `Git hygiene:` section when there's drift:

```
Git hygiene:
  unpushed commits: 3 (consider: git push)
  uncommitted: 5 modified/staged, 2 untracked (review with: git status)
  Guide: .claude/skills/session-start-git-hygiene.md
```

You are expected to investigate and resolve before doing new work. Ignoring the notice lets drift compound.

## Response flow

### Unpushed commits > 0

1. `git log --oneline @{u}..HEAD` — see what's unpushed
2. Decide:
   - **Your own completed work** → `git push`. Standard case.
   - **Midway through a feature** → push anyway (feature branches are yours; origin as backup never hurts), or continue and push at a natural checkpoint.
   - **Unsure if it's yours** → `git log --format='%an %s' @{u}..HEAD` to see authors. If `Co-Authored-By: Claude` appears on commits you don't remember, check STATE.md or recent session history before pushing.

### Uncommitted files

Review `git status` output:

- **Modifications to your own in-progress work** → commit or stash before context switching
- **Untracked files that look like build artifacts** (`*.tsbuildinfo`, `next-env.d.ts`, `__pycache__/`, logs) → add to `.gitignore` rather than commit or ignore
- **Files outside your scope** (`.claude/commands/*.md` modified by a recent `sync_infra` from core) → commit with `chore(infra): sync ...` message. These are propagations from core, safe to commit.
- **Legacy drift that pre-dates this session** (deletions from an old reorganization, unknown untracked dirs) → triage separately, not during session start. Make a note in STATE.md if you need to defer.

### Both clean

Proceed. Hook prints nothing; you see only the standard `[Session Context]` banner.

## Anti-patterns

- **Starting new work with drift visible and no plan to address it.** The drift compounds; next session has even more. Burn 2 minutes upfront.
- **`git push --force` without verifying upstream state.** Never force-push to master; for feature branches, only after confirming no one else works from that branch.
- **Committing unrelated files in one commit** just to clear `git status`. Split by concern (infra sync, feature work, config).
- **Ignoring `[RESTART REQUIRED]` from `sync_infra`** — see `.claude/skills/slash-command-hot-reload.md`. A stale slash-command cache won't show up in `git status` but will produce wrong behavior.

## Why not a constitutional requirement?

Article 14 covers end-of-phase discipline (STATE.md + Git + Notion). This is the symmetric start-of-session check. Promoting it to a constitutional article is reasonable but premature — start with automated hook + guide, observe whether agents actually act on the notice. If compliance is low, escalate to Article 14-mirror sub-article.

## Related

- `.claude/hooks/session-context.py` — the SessionStart hook that prints the summary
- CLAUDE.md 第十四条 — end-of-phase wrap-up (mirror principle)
- `.claude/skills/slash-command-hot-reload.md` — why sync_infra drift needs restart, not just commit
- `.claude/skills/lesson-classification.md` — why this is a guide (recurring behavior with clear trigger) rather than constitutional
