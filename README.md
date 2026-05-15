# governance-core

[![PyPI](https://img.shields.io/badge/PyPI-0.1.0a0-blue)](https://pypi.org/project/governance-core/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Reusable multi-agent governance infrastructure for Claude Code projects.**

Drop-in package providing a complete governance layer (constitution clauses,
safety hooks, proposal workflow, wrap-up discipline, cross-clone sync) so
you can focus on your project's business logic instead of re-inventing
multi-agent coordination from scratch.

## What you get

Install this package + run `governance-core install` in a new project, and
your project immediately has:

- **5 safety hooks** (PreToolUse + PostToolUse): scope-guard, edit-write-guard,
  session-boundary-guard, command-guard, sensitive-data-guard — all configurable
  via `.governance/config.json`
- **Proposal workflow** (`/proposal` skill): classify gate, draft / submit /
  approve / complete / archive state machine with audit trail
- **Wrap-up discipline** (`/wrap-up` skill): STATE.md + git + knowledge
  publishing + skill learning in one command
- **Constitution iteration** (`/iterate-constitution` skill): structured
  constitutional change workflow with red-line audit
- **Cross-clone coordination** (`/sync-infra`, `/sync-repos`): physical-files
  sync + cross-repo git operations
- **17 constitution clauses** (`art_00`..`art_16` + appendix) covering ritual,
  config management, contracts, scope governance, test/prod unification,
  git discipline, artifacts, constitutional protection, wrap-up discipline,
  memory staleness, etc.

## Quick start

This package is one half of a 2-piece distribution. The other half is
[multi-agent-template](https://github.com/napheir/multi-agent-template) — a
cookiecutter template + bootstrap CLI that generates a new project skeleton.

Typical workflow:

```bash
# One-time setup (per machine)
pip install cookiecutter
pip install governance-core
pip install multi-agent-bootstrap

# Per-project: one-line bootstrap
multi-agent-bootstrap new my-project \
    --agents core,data \
    --ritual-phrase "Acknowledged"

# Verify
cd ~/workshop-claude/my-project
governance-core doctor --project-root .
```

See [docs/architecture.md](docs/architecture.md) for the full picture
(generic vs business boundary, config injection mechanism, upgrade flow,
cross-clone coordination).

## Standalone CLI usage

You can also install governance-core directly into an existing multi-agent
project (without cookiecutter):

```bash
cd /path/to/your/project
pip install governance-core

# Write .governance/config.json with your project config
mkdir -p .governance
cat > .governance/config.json <<EOF
{
  "project_name": "my-project",
  "ritual_phrase": "OK",
  "core_agent_name": "core",
  "agents": [
    {"name": "core", "branch": "master", "clone_dir": "agent-core"}
  ]
}
EOF

# Render clauses + install hooks/skills
governance-core install --project-root .

# Validate
governance-core doctor --project-root .
```

Subsequent updates: `git pull` this repo, `pip install -e . --upgrade`,
then `governance-core upgrade --project-root /path/to/your/project` (this
preserves your `.governance/config.json` but refreshes clauses/hooks/skills).

## Example content disclaimer

Some clauses and knowledge docs in this package contain examples drawn from
the **upstream project** where governance-core was first developed (domain
terminology, pipeline names, broker/API references, agent name conventions).
These are **explanatory examples**, not requirements. Your project's
`.governance/config.json` supplies its own agent names, ritual phrase, and
clause keywords; the package's logic is project-agnostic.

A v1.0 release will template-ize all example tables; v0.1.0 ships with
disclaimers attached to mixed clauses and methodology docs.

## Project status

**v0.1.0-alpha** (2026-05):
- API may break between minor versions (0.1.x)
- Stable from 1.0.0 onwards
- Bug reports + PRs welcome

## License

MIT — see [LICENSE](LICENSE).

## Related

- [multi-agent-template](https://github.com/napheir/multi-agent-template) —
  companion cookiecutter template + bootstrap CLI
- Trade Agent (the project where this package was first developed) — private
