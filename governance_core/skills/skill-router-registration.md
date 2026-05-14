---
name: skill-router-registration
description: After producing any new skill (.claude/commands/*.md or .claude/skills/*.md), explicitly review knowledge/INDEX.routing.json for router trigger registration. Decide whether the skill body should auto-inject when user prompts contain related keywords, register if yes, document the decision if no. Closes the "skill exists but agent doesn't know to invoke it" gap.
theme: universal
owner: core
tags: [skill, router, prompt-context, registration, workflow]
---

# Skill Router Registration

**Single sentence**: Every newly produced skill must pass through a
router-registration review before being marked done.

This guide codifies a workflow that closes a recurring gap: a skill is
written, synced, even merged to master — but **no user prompt ever
auto-invokes it** because no router triggers were added. The skill exists
but is silent until the agent independently remembers to use it. Two
of the four skills produced in this session ran into this:

| Skill | Router registered? | When fixed |
|-------|--------------------|------------|
| `/iterate-constitution` | Yes (registered same commit as skill) | Q6 Phase 1 |
| `/proposal` | **NO** (user noticed mid-session) | Required separate fix turn |
| `/wrap-up` | NO (works because user always types it) | Borderline — discuss |
| `/learn` | NO (works because hooks force it as entry) | OK by enforcement |

The rule below makes the review **explicit** rather than relying on the
author remembering at the right time.

---

## What to ask when a new skill is created

```
1. What user-prompt phrasing would express the intent this skill solves?
   (write 5-10 candidate phrases, both English and Chinese if applicable)

2. Is any of that phrasing already a trigger in another route?
   (cat knowledge/INDEX.routing.json — avoid trigger collision)

3. Decision:
   - Workflow skill (multi-step, decision tree, checklist)
     → REGISTER. Triggers cover domain keywords + intent verbs.
   - Domain reference (look-up, troubleshooting)
     → REGISTER. Triggers cover symptoms / error signals.
   - One-shot tool wrapper (thin CLI alias)
     → SKIP router. Harness skill list + slash invocation enough.
   - Internal-only utility (only invoked by other skills/code)
     → SKIP router.
   - User-always-types-it skill (e.g., /wrap-up at phase end)
     → BORDERLINE. Register if user might also describe intent
        without typing the slash; skip if always invoked by name.

4. Trigger-quality check:
   - Each trigger ≥ 3 chars (validate_routing warns on shorter)
   - Specific phrases > single tokens ("P4 regression" not "P4")
   - Bilingual coverage if both Chinese and English are likely
   - Total triggers per route: 4-10 typical; > 15 likely too broad
```

---

## How to register

```bash
# 1. Add route entry to knowledge/INDEX.routing.json:
{
  "name": "<skill-name>-trigger",
  "triggers": ["...phrase 1...", "...phrase 2...", ...],
  "path": ".claude/commands/<name>.md",  # or .claude/skills/<name>.md
  "max_lines": 80
}

# 2. Validate schema:
python tools/validate_routing.py

# 3. Sync to all clones (INDEX.routing.json is in ALWAYS_COPY_FILES):
python tools/sync_infra.py --execute
```

---

## How to document a skip decision

If router registration is skipped, add a one-line note in the skill body
itself (typically at the bottom under "Triggers" or "Discovery"):

```markdown
## Discovery

This skill is invoked by direct slash command only; no router trigger
registered because <reason: thin CLI wrapper / internal utility / user
always types name explicitly>.
```

This way future agents reviewing the skill don't re-litigate the decision.

---

## When to apply this rule

This guide should be active in the agent's mind at any of:

- `Write` creates a file in `.claude/commands/*.md`
- `Write` creates a file in `.claude/skills/*.md` (excluding `learned/`)
- `/extract-skill` finishes its extraction
- `/iterate-constitution` Step 4 (when constitution decision tree Q4
  produces a new skill)
- `/wrap-up` Step 5 (Infra sync) — verify any skill added this phase
  was reviewed for router registration

---

## Anti-patterns

- ❌ "I'll add the router rule later" — later never comes (`/proposal`
  shipped without router for ~30 minutes; was caught only because the
  user noticed in the next turn)
- ❌ Single-token triggers: `triggers: ["proposal"]` matches every prompt
  about any kind of proposal (router will inject too eagerly)
- ❌ Forgetting Chinese counterparts: bilingual project, missing 中文
  triggers means half the prompts won't activate the route
- ❌ Adding the router rule but not running `validate_routing.py`
  (typos / unreachable paths only show up at audit time)
- ❌ Triggering on the skill's own filename (e.g., `triggers: ["proposal.md"]`)
  — users don't write filenames in prompts

---

## See also

- `.claude/skills/skill-injection-tiers.md` — broader skill discovery
  framework (router is the Tier C / on-demand path)
- `tools/validate_routing.py` — schema validator
- `knowledge/INDEX.routing.json` — the routing config itself
- `.claude/hooks/prompt-context-router.py` — hook that consumes the routes
- `feedback_skill_router_registration.md` — companion memory hook
