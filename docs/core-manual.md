# governance-core — core agent operations manual

How to develop the `governance-core` package now that the repository is
**self-hosted** (P-0066): governed by its own package, in its own Claude Code
session, in-boundary.

This manual is the operational companion to `constitution/total.md` 第十一条
(package source vs autonomy layer). The constitution states the rules; this
manual states the procedure.

## 1. The two layers — never confuse them

| Layer | Path | Role | git |
|-------|------|------|-----|
| **Package source** | `governance_core/` | The authoritative source of every governance asset. Edit here. | committed |
| **Autonomy layer** | root-level `.claude/{hooks,skills,commands,agents}/`, `tools/`, `contracts/`, `agent_rules/`, `knowledge/`, `.governance/clauses/` | The **self-installed instance** — what `governance-core install` copied out of the package source so this repo can be governed by it. Pure derivative. | gitignored |

The autonomy layer is a **snapshot**, produced by a copy-based installer (no
symlinks). The root-level `tools/proposal_lib.py` you see is a *copy* of
`governance_core/tools/proposal_lib.py`; the root `.claude/hooks/scope-guard.py`
is a copy of `governance_core/hooks/scope-guard.py`; and so on.

## 2. The dogfood loop — change source, then reinstall

To change any governance capability (a hook, a tool, a skill, a clause, a
contract):

1. **Edit the package source** under `governance_core/` — never the root-level
   autonomy-layer copy. Editing the copy is a dead end: the change is
   gitignored, never published, and silently overwritten on the next install.
2. **Reinstall into this repo:**
   ```pwsh
   governance-core upgrade --project-root .
   ```
   `upgrade` re-copies the package source into the autonomy layer while
   preserving `.governance/config.json`.
3. **Test in this repo.** Hooks read from `.claude/hooks/`; tools run from
   `tools/`. Until step 2 runs, this session is still executing the *old*
   snapshot.

> **Why this matters.** "A bug in the package shows up immediately in our own
> development" — the headline benefit of self-hosting — is only true if you
> reinstall after every source change. Skip step 2 and you are testing stale
> hooks/tools. The loop is: **edit `governance_core/` → `governance-core
> upgrade` → test.**

If you changed a hook, the new behavior only takes effect for hook events
fired *after* the reinstall (and, for some events, after the Claude Code
session reloads settings).

## 3. Where changes happen

governance-core changes are made **in this repository's own Claude Code
session** — open Claude Code with the working directory set to this repo.
The session boundary is this repo (`.git` toplevel), so all edits are
in-boundary. Cross-boundary "reach-in" from another project (the pre-P-0066
pain) is no longer used.

## 4. Proposals

This repo runs its own proposal pipeline:

- In-flight proposals live in `shared_state/proposals/core/` (gitignored —
  runtime state, constitution 第四条之一).
- Terminal proposals are archived by `/proposal archive` to
  `proposals/_archive/<YYYY>/` (committed — the durable governance record).
- The `/proposal` skill (`.claude/commands/proposal.md`) wraps the state
  machine; `tools/proposal_lib.py` is the CLI it calls.

## 5. Constitution changes

Edits to `constitution/total.md`, `constitution/agent.core.md`, and
`CLAUDE.md` must go through the `/iterate-constitution` skill
(constitution 第十三条); `edit-write-guard` blocks direct Edit/Write of those
three files. After authoring, `tools/regen_constitution.py` regenerates
`CLAUDE.md` (which is generated — never hand-edit it). Role detection reads
the `.role` file at the repo root (`core`).

## 6. Releasing

Version bump in `pyproject.toml` + `governance_core/__init__.py`, commit, then
draft & publish a GitHub Release — `.github/workflows/release.yml` builds and
publishes to PyPI via Trusted Publisher (P-0064). Releasing is an outward-facing
action: do it only with explicit human approval.

## 7. Topology-aware skills (P-0068)

The package ships the **complete** skill set, multi-agent capabilities
included. A consumer's topology — read from `.governance/config.json`'s
`agents` count — changes only which steps *run*, never which capabilities are
*present* (install-and-get-everything). For single-agent governance-core:

- **Multi-agent steps degrade to not-run.** `/publish-knowledge`,
  `/sync-repos`, `/sync-infra`, and `/wrap-up` Steps 2b/5/5b carry a topology
  gate — under single-agent topology they print
  `[N/A — single-agent topology — skipped]` and do nothing. The multi-agent
  capability stays fully shipped for multi-agent consumers.
- **Single-agent-applicable steps run.** Lesson classification, STATE.md
  upkeep, proposals, git — all run normally. Lesson archival reuses the
  `lesson-classification` skill verbatim; a self-hosted package authors a
  Skill guide in the package source `governance_core/skills/`, while learned
  skills stay in `.claude/skills/learned/` (kept committed by a `.gitignore`
  carve-out).
- **Skill extraction runs.** `/extract-skill` and `/wrap-up` Steps 4a–4c use
  the `governance_core.discovery` machinery, packaged by P-0069 — they run
  directly, no agent-core sibling clone, no `PYTHONPATH`.

Running `/wrap-up` in self-hosted governance-core therefore completes with
every step either applied or cleanly skipped — no broken step.

## 8. Hook wiring + skill-learning

`governance-core install` / `upgrade` emit `.claude/settings.local.json`,
registering every shipped hook from `hooks/hooks_manifest.json` (P-0067) —
hook wiring is install-and-get-everything, no hand-authoring. Groups tagged
`"_managed": "governance-core"` are regenerated on every upgrade; a project's
own hook groups are preserved (a pre-P-0067 hand-authored governance group is
auto-detected and migrated). The installer is a subprocess, so it can write
this critical-path file that an interactive agent cannot.

The skill-learning machinery is packaged too: P-0069 extracted it from
agent-core into `governance_core.discovery`, so `/extract-skill` and
`/wrap-up` Steps 4a–4c run the packaged tracker / extractor / registry
directly — no `../agent-core` sibling clone, no `PYTHONPATH`. Learned-skill
state stays in the consuming project's `.claude/skills/learned/`.
