# governance-core

Reusable multi-agent governance infrastructure for Claude Code projects.

**Status**: 0.1.0-alpha (P-0059 Phase 1 in-progress, not yet installable).

## What this provides

When installed via `pip install governance-core` and invoked via
`governance-core install` in a downstream project, the package gives that
project:

- **Hooks safety mechanisms**: scope-guard, edit-write-guard,
  session-boundary-guard, command-guard, sensitive-data-guard
- **Proposal mechanism**: full `/proposal` skill (classify / create / submit /
  approve / complete / reject / supersede / list / show), `proposal_lib` CLI,
  `shared_state/proposals/<agent>/` physical layout, `_id_ledger.json`
  cross-clone ID allocation
- **Wrap-up + knowledge curation**: `/wrap-up` / `/extract-skill` /
  `/update-skill` / `/learn` / `/publish-knowledge` / `/dashboard`
- **Constitution iteration**: `/iterate-constitution` skill +
  `audit_sub_constitutions.py` red-line checks
- **Cross-clone coordination**: `/sync-repos`, `/sync-infra`, per-branch
  `agent.md` `merge=ours` driver, project-aware ID ledger

## Distribution model

This package is half of the `multi-agent-template` + `governance-core` pair:

- **`multi-agent-template`** (cookiecutter): generates the project skeleton
  (CLAUDE.md framework, agent_rules templates, constitution scaffolding,
  N-clone bootstrap script)
- **`governance-core`** (this pip package): provides the implementation layer
  that the skeleton points to; can be independently `pip install --upgrade`-d

## Configuration

Downstream projects provide `.governance/config.json` with:

- `project_name`, `install_root`, `shared_state_root`, `claude_dir`
- `core_agent_name`, `core_branches`, `ritual_phrase`
- `agents[]` (name + branch + clone_dir per agent)
- `upstream_branch`, `constitution_layout`

`governance-core` reads this config and injects values into hooks, audit tools,
and constitution clauses at install time.

## Phase 1 status

This skeleton (commit chain starting from initial commit) contains only the
package structure. Generic resources are migrated in Phase 1.2-1.4 from
agent-core. See `audit/governance_package_inventory.md` and
`audit/governance_package_coupling.md` in agent-core for the migration plan.
