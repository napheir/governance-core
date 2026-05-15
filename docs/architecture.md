# governance-core — Architecture

Multi-agent governance-as-a-package. Generic constitution clauses + hooks +
skills + audit tools packaged so any new multi-agent Claude Code project can
inherit them with `pip install governance-core` + one `governance-core
install` invocation.

## Companion repo

This package is half of a 2-piece distribution:

| Repo | Role |
|------|------|
| **`governance-core`** (this) | Implementation layer (pip package) — clauses + hooks + tools + skills + contracts |
| **`multi-agent-template`** | Skeleton + bootstrap CLI (cookiecutter) — generates the project directory tree |

Downstream project = skeleton (from template) + governance assets (from this package, injected at install time).

## Generic vs business boundary

The core insight: in any multi-agent project, ~65% of the governance
infrastructure is generic (proposal flow, scope enforcement, hooks for
safety, wrap-up discipline, etc.). The remaining ~35% is business-specific
(data flow contracts, business agent topology, domain rules).

This package contains only the generic part. Business specifics stay in
the downstream project. The boundary is enforced at multiple layers:

| Generic (this package) | Business (downstream project) |
|------------------------|-------------------------------|
| `clauses/art_NN_*.md` (constitution articles) | `CLAUDE.md` business clauses (e.g., Art 6 data flow) |
| `hooks/scope-guard.py` etc. | `.claude/hooks/<business-hook>.py` (e.g., pipeline-check) |
| `skills/proposal.md` etc. | `.claude/skills/<business>.md` (e.g., generate-signals) |
| `tools/proposal_lib.py` etc. | `tools/<business>.py` (e.g., pnl_debugger.py) |
| `contracts/proposal_frontmatter_schema.md` | `contracts/<business>_contract.md` |
| `agent_rules/shared.*.txt` | `agent_rules/<agent>.allow.txt` |

## Config injection mechanism

Mixed-class tools (those whose logic is generic but data is project-specific)
read from the downstream project's `.governance/` directory at runtime:

```
<downstream-project>/.governance/
  ├── config.json           # project_name, install_root, shared_state_root,
  │                         # core_agent_name, ritual_phrase, agents[],
  │                         # upstream_branch, constitution_layout
  ├── core_keywords.json    # red-line clauses for audit +
  │                         # extra_protected_patterns for check_constitution_change
  ├── sync_files.json       # ALWAYS_COPY_FILES for sync_infra
  ├── data_source_entries.json  # prepare_dataset entry imports for data-source-guard
  └── clauses/              # rendered governance-core clauses with
                            # substitutions (e.g., ritual phrase)
      ├── art_00_ritual.md
      └── ...
```

Every tool that reads config has a fallback path: if `.governance/` files
are missing, generic empty/placeholder defaults kick in so bootstrap
doesn't deadlock. Onboarded projects always supply their own `.governance/`
(created by `governance-core install`), so fallbacks never surface in
normal operation.

Since P-0063 this also covers the three scope-security hooks/tools whose
business data was previously placeholder-substituted (which would silently
break them if consumed verbatim): `_guard_common.py` derives cross-repo
block patterns from `config.json`; `data-source-guard.py` reads
prepare_dataset entry imports from `data_source_entries.json`;
`check_constitution_change.py` appends `extra_protected_patterns` from
`core_keywords.json`.

## CLI subcommands

| Subcommand | Purpose |
|------------|---------|
| `install` | First-time setup: write config.json, copy assets to .claude/, render clauses, configure .gitattributes |
| `upgrade` | Refresh assets while preserving config.json (post-`git pull` of governance-core) |
| `doctor` | Verify config + hooks + clauses present and valid |
| `render-clauses` | Standalone clause render (used by template bootstrap; useful for surgical clone updates) |
| `version` | Print package version |

## Upgrade flow

When governance-core releases a new version (new clause / fixed hook /
better tool), downstream projects upgrade independently:

```pwsh
cd ~/workshop-claude/governance-core && git pull && pip install -e . --upgrade
cd ~/workshop-claude/my-project && governance-core upgrade --project-root .
```

`upgrade` preserves `.governance/config.json` (your customizations) but
refreshes `.governance/clauses/` + `.claude/` from the new package. Business
files (top-level CLAUDE.md, business hooks, business contracts) are never
touched.

## Cross-clone coordination

For multi-clone projects (one git clone per agent), each clone needs its
own `.governance/`. Two approaches:

1. **Full install per clone** — overwrites .claude/ etc. Good for fresh projects.
2. **Surgical bootstrap** — copy config JSONs + `render-clauses` only.
   Preserves clone-specific .claude/ content. See agent-core's
   `tools/bootstrap_governance_in_clones.py` (P-0059 Phase 2.5) for the
   surgical pattern.

## Dogfood case: agent-core (Trade Agent)

The package's first production user is agent-core itself — the project
where the package was extracted from. Phase 2 of P-0059 migrated
agent-core to consume governance-core, validating:

- `pip install -e ../governance-core` works from agent-core
- `.governance/config.json` with Trade Agent topology (5 agents,
  ritual=`如君所愿`) loaded by `load_config('.')`
- 17 clauses rendered with `如君所愿` substituted
- `audit_sub_constitutions`, `sync_infra`, `regen_constitution`,
  `migrate_proposals_to_shared_state` all read from `.governance/` with
  fallback
- `constitution/total.md` slim from 625 → 450 lines; CLAUDE.md 21459 →
  15322 chars (-28%)
- 10/10 regression tests pass (see agent-core
  `tests/regression/test_governance_dogfood.py`)

P-0059 Phase 2 only migrated config + clauses + a slim CLAUDE.md — agent-core
still kept its own copies of the generic hooks/tools. P-0063 closed that gap:
governance-core's copies were reconciled to the single authoritative version
(config-driven + sanitized), then agent-core adopted them via
`governance-core upgrade`. agent-core is now a *true* consumer — its generic
hooks/tools/skills are install-managed (refreshed by `upgrade`, never
hand-edited), so improving a common-layer capability means editing the
governance-core repo, not a local copy.

## Releasing

Both `governance-core` and `multi-agent-bootstrap` publish to PyPI via
**Trusted Publisher** (OIDC) — no API tokens. Each repo has
`.github/workflows/release.yml`:

- **GitHub Release published** -> build + publish to production PyPI
  (`environment: pypi`).
- **workflow_dispatch** (manual) -> build + publish to TestPyPI
  (`environment: testpypi`, `skip-existing`) — a rehearsal run.

To cut a release: bump the version in `pyproject.toml` + `__init__.py`,
commit, then draft & publish a GitHub Release — the workflow does the
rest. The local `twine` + `~/.pypirc` path remains as an emergency
fallback. Introduced by P-0064.

## Phase 3 status

| Capability | State |
|-----------|-------|
| Pip-installable | ✅ |
| CLI install/upgrade/doctor/render-clauses | ✅ |
| Cross-platform (Windows + POSIX) | ✅ |
| Cookiecutter template companion | ✅ |
| Cross-clone bootstrap | ✅ (surgical via render-clauses) |
| Logging in CLI output | ⏳ (basicConfig not yet wired; cosmetic) |
| PyPI release | ✅ [0.1.2](https://pypi.org/project/governance-core/) |
| GitHub repo URLs | ✅ [napheir/governance-core](https://github.com/napheir/governance-core) |
| Multi-clone N-agent scaffold | ✅ (multi-agent-bootstrap 0.2.0) |
