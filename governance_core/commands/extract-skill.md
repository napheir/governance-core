---
theme: universal
owner: core
---

# /extract-skill - Extract reusable skill from completed workflow

After completing a complex, multi-step workflow, use this command to capture it as a reusable skill document. Inspired by Hermes Agent's Skill Learning Loop.

## When to Use

- After completing a multi-step task that might recur (e.g., pipeline run, audit, data refresh)
- When you notice a workflow pattern worth preserving for future sessions
- When the user explicitly asks to save a workflow

## Workflow

1. **Analyze the completed work**: Review the current session's task list, recent commands, and outputs to identify the workflow pattern.

2. **Classify the layer** (P-0065): decide whether the skill is a
   **common-layer candidate** (generic — reusable by any governance-core
   consumer) or **business** (specific to this project). Use the
   generic-vs-project axis in the `lesson-classification` skill. When in
   doubt, choose `candidate-common` — a misclassification only costs one
   extra review at governance-core, whereas a missed candidate never
   surfaces. The choice becomes the `--layer` argument below and is written
   to the skill's `layer:` frontmatter; the candidate pipeline reads it.

3. **Extract the skill**: Use the extractor module. It ships in the
   governance-core package (`governance_core.discovery`); the generated skill
   is written to this project's own `.claude/skills/learned/`:
   ```bash
   python -m governance_core.discovery.extractor \
     --name "<kebab-case-name>" \
     --description "<one-line description>" \
     --steps "Step 1|Step 2|Step 3" \
     --preconditions "Check 1|Check 2" \
     --outputs "Output path 1|Output path 2" \
     --tags "tag1,tag2" \
     --notes "Caveat 1|Caveat 2" \
     --layer "candidate-common"
   ```

4. **Verify the generated skill**: Read the generated file at `.claude/skills/learned/<name>.md` (in your own repo) and confirm correctness — including the `layer:` frontmatter field set in step 2.

5. **Verify registry discovery**: Run the registry to confirm the new skill appears:
   ```bash
   python -m governance_core.discovery.registry --format table
   ```

> **Steps 6–8 (surfacing).** A learned skill is **auto-surfaced**: P-0118 puts
> every learned skill in the SessionStart universal-injection pool (it is this
> agent's own extraction), so it is consulted without any central catalog. The
> retired `knowledge/skills/_tiers.json` and its old hub/non-hub tier-cataloging
> steps are gone — there is nothing tier-shaped to edit, in any clone.

6. **(Optional) Cluster it for scenario recall.** The skill already surfaces via
   the universal pool. If it belongs to a task-shaped scenario, also add it to a
   cluster in `knowledge/skills/_scenario_clusters.json` (a `cluster -> members`
   map; schema in `knowledge/governance/skill-scenario-clusters.md`) so it
   surfaces under that scenario too. Owner-maintained, in scope for any clone.

7. **(Optional) Refresh the browse index.** `knowledge/skills/INDEX.md` is a
   human-browsable catalog now derived from each skill's `theme` (learned skills
   group under "Learned"). Rebuild it if you want the browse view current:
   ```bash
   python tools/build_skill_index.py
   ```

8. **Verify audit passes:**
   ```bash
   python tools/audit_knowledge.py
   # Check 11 (theme): [OK] N md-skills themed; INDEX.md up to date
   # Check 16 (if scenario clusters authored): [OK] N md-skills all surfaced
   ```

9. **Report to user**: Show the skill name, location, `layer` (candidate-common
   vs business), and a summary of what was captured.

## Notes

- Skills are stored in `.claude/skills/learned/` (auto-discovered by SkillRegistry)
- Use `--overwrite` flag if refining an existing skill (re-extract over the prior version)
- Follow kebab-case naming convention
- Reference: `knowledge/research/hermes_agent.md` (Section 2, Mechanism A)
- Browse existing skills by `theme` group with `python tools/skill_catalog.py` (or the generated `knowledge/skills/INDEX.md`)
