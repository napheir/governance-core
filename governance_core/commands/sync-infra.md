---
theme: core-only
owner: core
---

# /sync-infra - Check every clone's harness wiring

Read-only check, run from the core clone, that every business clone is wired the one way (P-0137). It changes nothing.

> **Topology gate (P-0068)** — multi-agent command. First read
> `.governance/config.json`; if `agents` has length 1 (single-agent
> topology), print `[N/A — single-agent topology — skipped]` and stop —
> there are no other clones to check (a self-hosted single-agent repo
> reflects package-source changes via `governance-core upgrade`).

## The one wiring model

- **gc-managed files and hook wiring**: `pip install -U governance-core`, then `governance-core upgrade --project-root <clone>` in every clone. Upgrade installs the files and registers every gc hook clone-locally (`${CLAUDE_PROJECT_DIR}/.claude/hooks/...`).
- **Tracked project files** (constitution source, project-authored skills and commands, routing tables): `/sync-repos` merges master into each clone.
- Nothing writes into another clone or registers a hook as an absolute path into core. Before 0.52.0, `tools/sync_infra.py --execute` copied files and did exactly that, so it fought upgrade. `--execute` is now refused with exit 2.

## When to use

- In `/wrap-up` Step 5 (multi-agent).
- After `/sync-repos`, and after upgrading the clones.
- When a clone behaves as if it runs core's hooks, or seems to miss a hook.

## Workflow

```bash
python tools/sync_infra.py                 # all business clones
python tools/sync_infra.py --agent <name>  # one clone
python tools/sync_infra.py --json          # machine-readable
python tools/sync_infra.py --project-root <core clone>   # check another project read-only
```

Clones are found next to the core clone: `<core clone's parent>/<agents[].clone_dir>`.

| check | level | meaning | fix (printed) |
|---|---|---|---|
| `clone-missing` | FAIL | the configured clone directory does not exist | fix `agents[].clone_dir`, or clone the branch there |
| `settings-missing` | FAIL | no readable `.claude/settings.local.json` | `governance-core upgrade --project-root <clone>` |
| `foreign-hook-ref` | FAIL | a hook command points outside the clone (e.g. core's `.claude/hooks/`) | upgrade; if the entry survives (a mixed group), remove it |
| `hook-unregistered` | FAIL | a hook in the clone's `hooks_manifest.json` is not registered clone-locally | upgrade |
| `wide-allow` | WARN | `Bash(rm:*)`, `Bash(del:*)`, `Bash(powershell:*)` or `Bash(pwsh:*)` in `permissions.allow` | the narrow replacements it lists; the owner applies them |
| `copy-drift` | WARN | a path in `.governance/sync_files.json` `always_copy_files` differs from core's (line endings ignored) | `/sync-repos`, then upgrade |

Exit codes: 0 = no FAIL, 1 = at least one FAIL, 2 = the check could not run.

## Notes

- Read-only: it never writes to any clone, so it is safe to run at any time.
- `.governance/sync_files.json` is now read only for the drift WARN.
