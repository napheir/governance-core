---
name: skill-injection-tiers
description: When registering or auditing any skill (command/guide/learned/module), decide its prompt-context injection tier per the lazy-no-reinject principle so always-on token cost stays minimal but every skill remains discoverable.
theme: universal
owner: core
tags: [skill-registry, prompt-context, hook-design, governance]
---

# Skill Injection Tiers

A design principle for *where every skill belongs in the prompt-context delivery
chain*. The single rule:

> **If something else already injects a skill (or its discovery handle), we do
> not inject it again. But every skill is still registered for management and
> on-demand recall.**

Without this rule, registry injection competes with the harness's auto-list
and we burn tokens shipping the same names twice every session.

---

## The four sources

`governance_core/discovery/registry.py` scans four sources and stamps each entry with
`source_type`:

| source_type | Physical path | Loaded by |
|-------------|---------------|-----------|
| `command`   | `.claude/commands/*.md` | Skill tool (lazy body); harness lists names+desc in system-reminder |
| `guide`     | `.claude/skills/*.md`   | Skill tool (lazy body); **no auto-listing anywhere** |
| `learned`   | `.claude/skills/learned/*.md` | Skill tool (lazy body); **no auto-listing**; per-agent state |
| `module`    | `skills/*/<name>.py`    | Python `import` (lazy); **no auto-listing**; not a slash command |

---

## The three injection tiers

| Tier | What lands in context | When | Source types covered |
|------|----------------------|------|----------------------|
| **A** | Name + 1-line description | SessionStart (once) | `learned` |
| **B** | Name + 1-line description | SessionStart (once) | `guide` |
| **C** | Full body | On-demand via Skill tool / `python -m` / router keyword | All four |

**Excluded from A/B**: `command` (harness already injects names+desc) and
`module` (not user-invocable; rarely needed in agent context).

The `--inject` mode of `governance_core.discovery.registry` emits tiers A+B together
as a single block; `session-context.py` (SessionStart hook, centralized via
`sync_infra` to all clones) appends it to the session banner.

---

## Why each rule

### Why commands are excluded from A/B

CC harness already prints a `system-reminder` block listing every
`.claude/commands/*.md` with name + description at session start. Registry
re-injecting the same list would waste ~2 KB/session for zero new info. The
only thing harness omits is the *score* (frequency × recency from tracker) —
not worth re-listing the whole roster for.

If an agent wants to see scores: `python -m governance_core.discovery.registry --format table`.

### Why guides are in tier B

Guides have no auto-discovery path. Harness doesn't list them. The Skill tool
can load any guide by name, but the agent has to *know the name first*.
SessionStart injection is the only reasonable channel — without it, guides
are write-only.

A guide that nobody recalls is equivalent to a guide that doesn't exist;
designing a guide implicitly commits to its discoverability.

### Why learned skills are in tier A

Same as guides, plus: learned skills are **per-agent session extractions**.
Each agent's clone has its own `.claude/skills/learned/` subset. Without
SessionStart injection, the agent forgets its own past extractions across
sessions — making the whole `/extract-skill` pipeline pointless.

### Why modules are excluded

Python modules under `skills/*/` are imported by other code (training
pipelines, indicator skill calls). They're not user-invocable and don't
appear in agent reasoning loops. Their L0 metadata exists for `python -m
governance_core.discovery.registry` discoverability only.

---

## When you add a new skill, ask three questions

1. **Will another mechanism auto-inject this?**
   - Yes (e.g., harness lists `.claude/commands/`) → exclude from A/B
   - No → continue to question 2

2. **Does the agent need passive recall, or only active recall when triggered?**
   - Passive (cross-cutting design principle) → tier B (guide)
   - Active (specific workflow on user trigger) → command (harness handles)
   - Active (session-internal workflow) → tier A (learned)

3. **Is there a token-cheaper trigger than SessionStart?**
   - If a UserPromptSubmit router can match keywords to load on demand → tier C
   - If the skill is critical-path for every session → A/B

---

## Anti-patterns

- ❌ Injecting commands at SessionStart (duplicates harness output)
- ❌ "Just inject everything — tokens are cheap" (death by a thousand 50-token cuts; cache also pollutes)
- ❌ Per-turn injection of stable lists (UserPromptSubmit fires every prompt; SessionStart fires once. Hot sets belong in SessionStart)
- ❌ Putting `print()` in `session-context.py` for skill output without checking the constitutional-review hook (Art.7 — use `sys.stdout.write` or the dedicated registry CLI)
- ❌ Hand-listing skills in the constitution or any other doc (registry is the single source of truth; the doc rots, registry stays correct)

---

## See also

- `governance_core/discovery/registry.py` — `manifest_for_injection()` is the filtering point
- `.claude/hooks/session-context.py` — `_emit_skill_injection()` calls registry --inject
- `proposals/slim_constitution_via_registry_and_router.md` — the larger architectural context
- `lesson-classification.md` — decides whether a session learning becomes a guide, learned, memory, or discard in the first place
