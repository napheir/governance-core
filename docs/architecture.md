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
| `install` | First-time setup: verify authorization code + candidate-uplink consent (P-0065), write config.json, copy assets to .claude/, render clauses, configure .gitattributes |
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

## Dogfood case: governance-core itself (self-hosting)

Since P-0066, `governance-core` is also its **own** consumer. The repo was
onboarded as a single-core-agent governed project: `governance-core install`
self-installs the governance layer into the repo, so changes to the package
are now made *in governance-core's own Claude Code session, in-boundary* —
no more cross-boundary reach-in from another project.

The "repo ⊃ package" split keeps source and self-installed instance distinct:

| | Path | git |
|--|------|-----|
| Package **source** (authoritative) | `governance_core/` | committed |
| **Autonomy layer** (self-installed instance — pure derivative) | root `.claude/{hooks,skills,commands,agents}/`, `tools/`, `contracts/`, `agent_rules/`, `knowledge/`, `.governance/clauses/` | **gitignored** |
| Runtime state | `shared_state/` (in-flight proposals) | gitignored |
| Authored config / constitution | `.governance/config.json`, `.role`, `constitution/`, `CLAUDE.md`, `.claude/settings.local.json` | committed |

The autonomy layer is gitignored because, for a single-repo single-agent
project, install artifacts are pure derivatives (`governance-core install`
regenerates them) with no other clone to propagate to — committing them would
be committing `dist/`. A fresh clone runs `governance-core install
--project-root .` to materialize the layer. The pip build is unaffected:
`packages.find` is limited to `governance_core*`, so wheel + sdist never
contain the autonomy layer.

The dogfood loop: edit `governance_core/` → `governance-core upgrade
--project-root .` → test. Because the installer is copy-based, the autonomy
layer is a snapshot — a source change is only exercised after the reinstall.
See `docs/core-manual.md` for the operations manual and
`constitution/total.md` 第十一条 for the governing clause.

## Config-aware skills (single-agent degradation)

P-0066 made the constitution *clauses* topology-aware (multi-agent articles
degrade for a single-agent project) but left the *skills* as their original
multi-agent versions — so `/wrap-up`, the skill Art.14 mandates, was
~half-inapplicable to self-hosted governance-core. P-0068 closed that gap
under one principle: **install-and-get-everything** — the package always
ships the complete capability set; a consumer's topology
(`.governance/config.json` `agents` count) changes only which steps *run*,
never which capabilities are *present*.

Each shipped skill step is one of three buckets:

| Bucket | Treatment |
|--------|-----------|
| **A — broken path** | Hardcoded cross-repo references (`../agent-core`, absolute paths) — de-hardcoded; a bug in any topology. |
| **B — genuinely multi-agent** | Cross-clone / cross-agent steps — under single-agent topology they degrade to **not-run** (an explicit `[N/A — single-agent topology — skipped]`). The multi-agent capability stays fully shipped. |
| **C — runs single-agent too** | Lesson classification, skill extraction, STATE.md — **fixed so they run**, not skipped: the existing decision logic is reused verbatim, only topology-dependent edges (paths, git treatment) adapt. |

The skill-learning machinery was found unpackaged and spun out to P-0069,
which extracted it from agent-core into `governance_core.discovery` — so
`/extract-skill` and `/wrap-up` Steps 4a–4c run the packaged machinery
directly (no `../agent-core` sibling clone, no `PYTHONPATH`). The installer
also seeds an initial `STATE.md` and emits `.claude/settings.local.json` — registering
every shipped hook from `hooks/hooks_manifest.json` (P-0067) — so a
consumer's hooks are wired on install, with no hand-authoring.

## Authorization model (P-0065)

From version 0.2.0 governance-core is **source-available, authorized-use**:
the source is public, but *using* it to govern a project requires a
maintainer-issued authorization code.

- **Codes are Ed25519-signed.** The maintainer holds the private signing key
  offline; the package ships only the public key
  (`governance_core/auth/pubkey.json`). `install` / `upgrade` verify codes
  **offline** — no phone-home, no network.
- **Two install-time gates.** `install` verifies the authorization code, then
  requires candidate-uplink consent (mandatory in the current version). Both
  must pass *before* the autonomy layer is materialized — so no valid code,
  or declined consent, means the governance capabilities are never copied
  into the project.
- **Runtime enforcement.** The install-time gate alone does not cover a
  project that was installed with a valid code and later loses authorization
  (code tampered, key rotated, code deleted) — its already-materialized hooks
  and tools would keep running. So a PreToolUse hook (`auth-guard.py`,
  matcher `*`) re-verifies the stored code before *every* tool call and
  blocks it when authorization is invalid. With all tool calls blocked the
  agent is frozen — hooks fail directly, proposal/wrap-up/skills fail
  transitively (their tools are frozen). The verdict is cached per (repo,
  code, public key) so the Ed25519 verify runs once, not per call. The freeze
  affects the agent only; a human re-authorizes from a terminal.
- **The code doubles as identity.** The verified `consumer_id` is written to
  `.governance/config.json` and will stamp the `origin` of capability
  candidates uploaded back to governance-core (later P-0065 phases).
- **Not DRM.** The source is readable Python; the check can be patched out.
  The code is a deterrent + an identity + a terms-of-use boundary, not an
  unbreakable lock. The license changed from MIT to a source-available
  authorized-use license at 0.2.0; releases 0.1.2–0.1.6 remain MIT.

Maintainer tooling (`maintainer/gen_signing_key.py`,
`maintainer/issue_auth_code.py`) is committed for auditability but excluded
from the pip package. See `docs/core-manual.md` §9 for the issuing workflow.

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
