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

> **Steps 6–8 are role-dependent.** `knowledge/skills/_tiers.json` and
> `knowledge/skills/INDEX.md` are **hub-owned**. If your clone is the
> **convergence hub** (the governance-core self-host: `.governance/config.json`
> `authorization.consumer_id` == `governance-core`, role core) follow the **Hub
> path** below. A **non-hub business / consumer clone** follows the **Non-hub
> path** further down — it cannot edit the hub-owned catalog in scope, and the
> hub catalogs the skill for it via a later sweep (gc #101 / P-0104).

### Hub path (core agent)

6. **Classify the skill's tier**: Decide which organizational tier the new skill belongs to and update `knowledge/skills/_tiers.json`:
   - **`universal`** — reusable in any Claude Code project (no Trade Agent coupling)
   - **`project`** — depends on Trade Agent infra (multi-clone / Futu / shared_state / contracts), cross-agent
   - **`branch`** — bound to a specific agent's business domain (rules / trade / data)
   - **`unclassified`** — only if you genuinely cannot decide now; must be reclassified before next `/wrap-up` (audit warns on non-empty unclassified)

   Edit `knowledge/skills/_tiers.json` and append the skill name to the chosen tier's `skills` array (keep array sorted alphabetically).

6b. **Surface the skill** (P-0103, gc #100): a tier classification is not
   enough — a skill is only ever **consulted** if it enters the SessionStart
   surface (第十五条 技能咨询纪律). Ensure the new skill is either in the
   **`universal`** tier (surfaced every session) OR a member of a **scenario
   cluster** in `knowledge/skills/_scenario_clusters.json` (a `cluster ->
   members` map; schema in `knowledge/governance/skill-scenario-clusters.md`).
   A `project` / `branch` skill that sits in no cluster is never surfaced and
   stays dead weight — `audit_knowledge.py` Check 16 FAILs on it once any
   scenario clusters are authored.

7. **Rebuild the skill index**: Run the builder so `knowledge/skills/INDEX.md` reflects the new skill:
   ```bash
   python tools/build_skill_index.py
   ```

8. **Verify audit passes**: Confirm bijection holds (every skill classified, no phantoms):
   ```bash
   python tools/audit_knowledge.py
   # Check 11 must report: [OK] N md-skills classified across 3 tier(s); INDEX.md up to date
   # Check 16 (if scenario clusters authored): [OK] N md-skills all surfaced (universal or clustered)
   ```

### Non-hub path (business / consumer agent)

You own your skill file and your own scenario clusters, but **not** the
reuse-tier catalog. Do only the in-scope steps; the hub catalogs the rest via a
later sweep.

6N. **Surface via your own scenario cluster** (replaces steps 6 / 6b / 7): add
   the new skill to a cluster in your `knowledge/skills/_scenario_clusters.json`
   (owner-maintained, in scope) so it enters your SessionStart surface (第十五条
   技能咨询纪律). Schema: `knowledge/governance/skill-scenario-clusters.md`.

7N. **Skip the hub-owned catalog steps**: do **not** edit
   `knowledge/skills/_tiers.json` and do **not** rebuild
   `knowledge/skills/INDEX.md`. They are hub-owned — a local edit is out of scope
   and `governance-core upgrade` would overwrite it.

8N. **Treat the catalog audit as WARN-pending, not FAIL**: in a non-hub clone
   `audit_knowledge.py` Check 11 / Check 16 record a just-extracted,
   not-yet-cataloged **learned** skill as `WARN: ... pending hub catalog` (gc
   #101 / P-0104) — NOT a failure. Do **not** roll back the extraction on that
   WARN. The hub later picks up the skill (it carries `layer: candidate-common`
   from step 2) via its cataloging sweep and assigns the tier + rebuilds INDEX
   centrally.

9. **Report to user**: Show the skill name, location, chosen tier (or
   `pending hub catalog` for a non-hub clone), layer, and a summary of what was
   captured.

## Notes

- Skills are stored in `.claude/skills/learned/` (auto-discovered by SkillRegistry)
- Use `--overwrite` flag if refining an existing skill
- For incremental refinement, use `refine_skill()` from `governance_core.discovery.extractor`
- Follow kebab-case naming convention
- Reference: `knowledge/research/hermes_agent.md` (Section 2, Mechanism A)
- Tier decision is informed by `knowledge/skills/INDEX.md` examples — browse with `python tools/skill_catalog.py` to see what each tier currently contains
