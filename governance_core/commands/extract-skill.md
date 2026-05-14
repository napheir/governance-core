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

2. **Extract the skill**: Use the extractor module to generate a skill document. Code lives in `agent-core`, but the generated skill belongs to the invoking agent's own `.claude/skills/learned/` — so set `PYTHONPATH` instead of `cd`-ing into core:
   ```bash
   PYTHONPATH="$(git rev-parse --show-toplevel)/../agent-core" \
   python -m skills.discovery.extractor \
     --name "<kebab-case-name>" \
     --description "<one-line description>" \
     --steps "Step 1|Step 2|Step 3" \
     --preconditions "Check 1|Check 2" \
     --outputs "Output path 1|Output path 2" \
     --tags "tag1,tag2" \
     --notes "Caveat 1|Caveat 2"
   ```

3. **Verify the generated skill**: Read the generated file at `.claude/skills/learned/<name>.md` (in your own repo) and confirm correctness.

4. **Verify registry discovery**: Run the registry to confirm the new skill appears:
   ```bash
   PYTHONPATH="$(git rev-parse --show-toplevel)/../agent-core" \
   python -m skills.discovery.registry --format table
   ```

5. **Classify the skill's tier**: Decide which organizational tier the new skill belongs to and update `knowledge/skills/_tiers.json`:
   - **`universal`** — reusable in any Claude Code project (no Trade Agent coupling)
   - **`project`** — depends on Trade Agent infra (multi-clone / Futu / shared_state / contracts), cross-agent
   - **`branch`** — bound to a specific agent's business domain (rules / trade / data)
   - **`unclassified`** — only if you genuinely cannot decide now; must be reclassified before next `/wrap-up` (audit warns on non-empty unclassified)

   Edit `knowledge/skills/_tiers.json` and append the skill name to the chosen tier's `skills` array (keep array sorted alphabetically).

6. **Rebuild the skill index**: Run the builder so `knowledge/skills/INDEX.md` reflects the new skill:
   ```bash
   PYTHONPATH="$(git rev-parse --show-toplevel)/../agent-core" \
   python tools/build_skill_index.py
   ```

7. **Verify audit passes**: Confirm bijection holds (every skill classified, no phantoms):
   ```bash
   PYTHONPATH="$(git rev-parse --show-toplevel)/../agent-core" \
   python tools/audit_knowledge.py
   # Check 11 must report: [OK] N md-skills classified across 3 tier(s); INDEX.md up to date
   ```

8. **Report to user**: Show the skill name, location, chosen tier, and a summary of what was captured.

## Notes

- Skills are stored in `.claude/skills/learned/` (auto-discovered by SkillRegistry)
- Use `--overwrite` flag if refining an existing skill
- For incremental refinement, use `refine_skill()` from `skills.discovery.extractor`
- Follow kebab-case naming convention
- Reference: `knowledge/research/hermes_agent.md` (Section 2, Mechanism A)
- Tier decision is informed by `knowledge/skills/INDEX.md` examples — browse with `python tools/skill_catalog.py` to see what each tier currently contains
