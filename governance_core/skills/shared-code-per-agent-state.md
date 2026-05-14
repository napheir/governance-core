---
theme: universal
name: shared-code-per-agent-state
description: When building multi-agent Python infrastructure where code lives in one canonical repo (agent-core) but multiple agent clones invoke it, separate code location from state location. Route code via PYTHONPATH; keep state in invoker's repo via resolve_project_root(). Never cd into a non-owned clone — it pollutes cross-repo state and trips scope guards.
type: guide
tags: [governance, cross-agent, infrastructure, scope, python, design-pattern]
created: 2026-04-17
updated: 2026-04-17
---

# shared-code-per-agent-state

Design pattern for any shared Python module that multiple agents invoke. Code stays in one canonical repo; state follows the invoker.

## When to apply

- Building or extending a module that multiple agents will `python -m ...`
- Writing shell commands in `.claude/commands/*.md` destined for `sync_infra` propagation
- Reviewing any `cd ../agent-* && ...` pattern — usually wrong
- Debugging scope-guard blocks on what looks like a legitimate tool invocation
- Touching the skill-learning loop (tracker / extractor / registry) or anything else under `skills/discovery/`

## The pattern

1. **Code stays in `agent-core`.** One canonical implementation; centrally maintained.
2. **State follows the invoker.** Each agent clone owns its own `.claude/skills/learned/` and any other per-session artifacts.
3. **Invocation uses `PYTHONPATH`, not `cd`:**
   ```bash
   PYTHONPATH="$(git rev-parse --show-toplevel)/../agent-core" \
   python -m skills.discovery.tracker --should-extract
   ```
   The shared module is importable, but CWD stays in the invoking agent's repo so state writes go there.
4. **Path resolution inside the module** uses `skills.discovery.resolve_project_root(__file__)`:
   - env `CLAUDE_AGENT_ROOT` (explicit override)
   - `git rev-parse --show-toplevel` from CWD
   - module-file parent as last-resort fallback
5. **Shared read-only assets** (Python skill modules, guide skills) reference `skills.discovery.CODE_ROOT` directly — this constant is derived from the module's `__file__` and always points to `agent-core`.

## Anti-patterns

| Anti-pattern | Why it breaks |
|--------------|---------------|
| `cd ../agent-core && python -m ...` | CWD changes; state writes land in core, mixing per-agent session data and tripping scope guards. |
| `Path(__file__).parent.parent.parent` as state path | Ties state to code location; every agent writes to agent-core. |
| Copying shared modules into each clone | Duplicates maintenance; breaks the centralized-code contract; `skills.discovery.registry` already handles discovery via `CODE_ROOT`. |
| Writing templates in core without testing from another clone | Core has no scope boundaries to trip, so scope issues only surface for other agents. |

## Checklist when extending shared infra

- [ ] Do module constants use `resolve_project_root()` for write paths?
- [ ] Do constants use `CODE_ROOT` for shared read-only reads?
- [ ] Does the slash-command template use `PYTHONPATH=` rather than `cd`?
- [ ] Did I run it from a non-core clone (e.g. `agent-rules`) and verify state landed there?
- [ ] After template edits, did I run `python tools/sync_infra.py --execute`?

## Origin

2026-04-17 skill-learning loop failure. `/wrap-up` template used `cd ../agent-core && python -m skills.discovery.tracker` which:
1. Looked like a cross-repo call to scope-guard observers.
2. Wrote `.usage.json` into `agent-core`, mixing session state across agents.

Fix introduced `skills.discovery.resolve_project_root()` / `CODE_ROOT`, updated `tracker.py` / `extractor.py` / `registry.py` to split code-vs-state, and rewrote `wrap-up.md` / `extract-skill.md` to use `PYTHONPATH`.

## Related

- `skills/discovery/__init__.py` — resolver + `CODE_ROOT` constant
- `.claude/commands/wrap-up.md` step 4 — reference invocation pattern
- `.claude/skills/lesson-classification.md` — how this ended up as a guide rather than memory
- `tools/sync_infra.py` — propagates updated templates; run after any slash-command edit
