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

## 9. Authorization (P-0065)

Since P-0065, `governance-core install` / `upgrade` are gated on a
maintainer-issued **authorization code** plus a **candidate-uplink consent**.
Both gates run before any autonomy-layer file is materialized — a failed gate
leaves the project with no governance capabilities.

Authorization is also enforced **at runtime**: the `auth-guard.py` PreToolUse
hook (matcher `*`) runs before every tool call, with two gates:

1. **Code verification** — the stored code must verify against the bundled
   public key and not be expired. The verdict is cached per (repo, code,
   key, date), so an expired lease is re-checked daily, never served stale.
2. **Revocation** (schema-2 codes) — the code's `consumer_id` must not be on
   the maintainer's signed revocation feed. `auth-guard` polls the feed URL
   carried in the code at most once per TTL (~6h), caching the last verified
   feed. An unreachable feed falls back to the cached copy; once no
   successful fetch has happened for the code's `max_offline_days`, the
   consumer is frozen. A schema-1 (legacy perpetual) code carries no feed
   and skips this gate.

A project that loses authorization — code tampered, lease expired, key
rotated, or `consumer_id` revoked — is frozen, not silently allowed to keep
running. The freeze affects the agent only; recover by re-running
`governance-core install` from a terminal, except a revocation, which only
the maintainer can lift.

The package ships an Ed25519 public key (`governance_core/auth/pubkey.json`);
the matching private key stays with the maintainer, outside the repo.
Authorization codes are verified **offline**; the revocation feed is the one
governance asset fetched over the network — it is signed, so it cannot be
forged or replayed empty. See `constitution/total.md` and the P-0065 /
P-0071 proposals for the model.

### Issuing codes (maintainer side)

The signing keypair is generated once:

```pwsh
python maintainer/gen_signing_key.py
```

It writes the private key to `~/.governance-core/signing_key.json` (never
committed, never packaged — `maintainer/` is excluded from the pip build) and
the public key to `governance_core/auth/pubkey.json` (committed, shipped).
**Back up the private key offline** — it cannot be recovered and signs every
code.

Issue one code per consumer:

```pwsh
python maintainer/issue_auth_code.py --consumer-id <project-or-org>
```

Codes are issued as **schema-2 leases** (P-0071): each carries an `expiry`
(default: issued + 365 days) plus the revocation-feed coordinates
(`revocation_feed_url`, `max_offline_days`). A lease is renewed by
re-issuing before expiry. `--schema 1` issues a legacy perpetual code;
`--expiry YYYY-MM-DD` overrides the lease window. The expiry is enforced by
the codec and by the runtime `auth-guard` (whose verdict cache is
date-keyed, so an expired code is never served a stale `valid` verdict).
The printed `GC1.<...>` string is the authorization code. `issue_auth_code`
also prints, on stderr, a **ready-to-paste install block** — `pip install`,
the auth code as a shell variable, and the `governance-core install` /
`doctor` commands. Hand that whole block to the consumer out-of-band: the
variable form (`CODE='...'`) keeps the long code intact through copy-paste
line wrapping, which a bare inline `--auth-code <long-code>` does not.

### Revoking a consumer (maintainer side)

To eject a consumer that has left the organization, add it to the signed
revocation feed:

```pwsh
python maintainer/revoke_consumer.py --consumer-id <id> --reason "left org"
```

This appends the consumer to `revocation.json`, re-signs it as
`revocation.json.sig`, and marks the consumer revoked in
`consumer_registry.json`. **Commit and push both feed files** -- the feed
is published at `revocation.json` on `master` and polled raw by every
consumer's `auth-guard` (P-0071 Phase 3 — at most once per ~6h TTL).
`--list` verifies and prints the current feed; `--init` writes a fresh
empty signed feed (`--force` overwrites an existing one).

The feed is signed with the same private key as authorization codes and
verified with the bundled public key, so it cannot be forged or replayed
empty. Revocation reaches a consumer on its next feed poll -- it does not
require the consumer to upgrade or cooperate. A determined consumer who
edits or deletes their own `auth-guard.py` cannot be frozen this way (the
verifier runs on their hardware) -- see the P-0071 proposal Non-Goals.

### Candidate attribution and the consumer registry

Every candidate envelope carries an `origin` — the `consumer_id` of the
project that produced it. At uplink time `origin` is verified against the
project's authorization code: the code is signed, so its `consumer_id` is
authentic, and `python tools/candidate.py uplink` / `submit` aborts if
`origin` does not match. A candidate cannot be uplinked under a forged
origin.

`maintainer/consumer_registry.json` (committed, maintainer-side) is the
ledger of every issued consumer — `consumer_id`, `status`
(`active` / `revoked`), `first_issued` / `last_issued`, current `expiry`,
plus the curation decision on each candidate. `issue_auth_code.py` records
a consumer on issuance; `revoke_consumer.py` flips its `status` to
`revoked`.

Hub-side curation enforces revocation on the contribution side too:
`candidate.py review` and `candidate.py promote` both consult the
registry, and a candidate whose `origin` is a revoked consumer is
hard-rejected — `review` flags it `[REVOKED ORIGIN]`, `promote` refuses to
fold it into the package source and records the rejection. Once an owner
leaves the organization, GC stops both running their governance (the
revocation feed) and accepting their common-layer contributions.

### Self-hosted governance-core

governance-core is its own first authorized consumer. Its
`.governance/config.json` carries an `authorization` block (consumer_id
`governance-core`) and a `candidate_uplink` consent block. `upgrade`
re-verifies the stored code on every run, so the dogfood loop is unchanged
except that `upgrade` now also checks authorization. `doctor` reports the
consumer id and fails (exit 7 / 8) if authorization or consent is missing.

### Rotating the key

If the private key leaks: regenerate (`gen_signing_key.py --force`), commit
the new `pubkey.json`, release a new package version, and re-issue codes.
Old codes stop verifying once the new public key ships.

## 10. Install-managed manifest (P-0065)

`install` / `upgrade` write `.governance/installed_files.json` — a manifest
of every file the installer materialized, each with a content sha256
baseline, source `governance-core` version, and category. It is the
authoritative answer to "is this path install-managed or business?" and the
baseline for drift detection in later P-0065 phases.

Query a path with the shipped tool:

```pwsh
python tools/whichlayer.py .claude/hooks/scope-guard.py   # -> install-managed
python tools/whichlayer.py CLAUDE.md                      # -> business
```

Exit codes: `0` install-managed, `1` business, `2` error (no manifest). The
manifest is a pure derivative — regenerated every install/upgrade — so it is
gitignored, like the autonomy layer it indexes.

The manifest also drives **prune** (P-0070): on `upgrade`, a path the
*previous* manifest recorded but the new install no longer produces is a
stale file (its package source was removed) and is deleted, with a `[prune]`
report on stderr. Manifest-diff is the safety boundary — only previously
install-managed paths are eligible, so business / authored files and the
`.claude/skills/learned/` carve-out are never pruned. Prune runs after drift
capture, so a stale file that was locally edited is first captured as a
candidate. `governance-core upgrade --no-prune` keeps stale files.

## 11. Candidate pipeline (P-0065)

governance-core is the convergence hub for common-layer improvements: the
candidate pipeline collects them from consumers, transports them, and
curates them back into the package. See `docs/architecture.md` for the
model; this section is the operations side.

### Consumer side — contributing a candidate

- **Net-new skills**: a learned skill tagged `layer: candidate-common` is
  packaged by `python tools/candidate.py collect`.
- **Active submission**: `/submit-candidate` packages a chosen capability —
  backed by `python tools/candidate.py submit ...`.
- **Drift**: `upgrade` automatically captures locally-edited install-managed
  files as drift candidates (reported on stderr).

All three stage envelopes under `.governance/candidate-outbox/`. Uplink one
with `python tools/candidate.py uplink <envelope-dir>` (`--dry-run` previews
without sending). The payload is secret-scanned before it leaves the
project, and uplink is consent-gated.

### The trigger — `sweep` in `/wrap-up` (P-0072)

A staged candidate that is never uplinked never reaches the hub. P-0072
wires the **trigger**: `/wrap-up` step 4d runs

```pwsh
python tools/candidate.py sweep
```

`sweep` collects `candidate-common` skills and uplinks every one whose
payload digest is absent from the dedup ledger
(`.governance/candidate-outbox/_uplinked.json`) — so the same skill is
sent once, an edited skill is re-sent, and a phase with no new candidate
is a clean skip. `sweep` degrades to a report (never a non-zero exit) when
consent, network, or `gh` is unavailable, so it cannot stall a wrap-up.
The hub project (governance-core itself) has nothing to uplink and skips.

The `candidate-reminder.py` SessionStart hook (P-0072 Phase 2) backs the
trigger: at every session start it counts `candidate-common` learned
skills absent from the uplink ledger and surfaces them in the startup
banner — so an un-uplinked candidate stays loudly visible even if
`/wrap-up` is skipped entirely. The hook is silent for the hub project.

### Hub side — curating incoming candidates

As governance-core's maintainer:

```pwsh
python tools/candidate.py review                  # list incoming candidates
python tools/candidate.py promote <envelope-dir>  # promote into the source
python tools/candidate.py promote <envelope-dir> --decision rejected --note "..."
```

`review` scans local `candidates/` envelopes and open GitHub issues labelled
`candidate`. `promote` copies a promoted skill / hook into the package
source (`governance_core/skills/` or `governance_core/hooks/`); a `mechanism`
is listed for manual placement. Every decision is written to
`maintainer/consumer_registry.json` — the committed curation ledger.
Promotion is a judgment call: the tooling collects and presents; the
maintainer decides. A promoted capability reaches every consumer through the
next release.

## 12. Consumer updates (P-0073)

A consumer updates governance-core in two steps:

```pwsh
pip install -U governance-core              # fetch the new wheel
governance-core upgrade --project-root .    # re-materialize the autonomy layer
```

`upgrade` alone re-materializes from the *installed* package, so the
`pip install -U` must come first to actually move versions.

**Install governance-core into an isolated venv per consumer project.**
`governance-core` is a normal PyPI package, so a bare `pip install
governance-core` resolves against whatever environment is active. On the
governance-core maintainer's own machine the global Python carries the
**editable** install of the gc repo (metadata version `0.1.0a0`): there a
bare `pip install governance-core` reports "requirement already satisfied"
and does not fetch the release, while `pip install -U` would *uninstall
the editable install* and break the self-hosted dogfood. A per-project
venv (`python -m venv .venv` then activate) avoids both: the consumer
project gets a clean environment, and the maintainer's editable install is
never touched. Run `governance-core install` / `upgrade` with that venv
active.

The `update-reminder.py` SessionStart hook (P-0073 Phase 1) closes the
"owner never remembers" gap: at session start it compares the autonomy
layer's recorded version (`installed_files.json` →
`governance_core_version`) with the latest release on PyPI, and when a
newer one exists prints the update command in the startup banner. The
PyPI query is TTL-cached (~12h); an unreachable PyPI or any error is
silent, and the hub project (governance-core itself, an editable install)
is silent. It only notifies — upgrading stays the owner's deliberate
choice.

Before applying an upgrade, preview it (P-0073 Phase 2):

```pwsh
governance-core upgrade --dry-run --project-root .
```

`--dry-run` runs the full upgrade computation — the overwrite set, drift
detection, prune set, version delta — through the *same* code path as a
real upgrade, but writes nothing. It reports how many install-managed
files would be overwritten, the version delta (with a minor-skew note
pointing at `contracts/` when the jump crosses minor lines), and for
every locally-edited install-managed file a **unified diff** of the
consumer's current content vs the incoming package version — so a
personalized common-layer file's divergence from upstream is visible
before it is overwritten. It also lists local additions (owner-authored
files that are not install-managed) so they can be reviewed against the
incremental changes. The real `upgrade` is unchanged.

The `/upgrade` skill (P-0073 Phase 3) is the recommended way to apply an
update: it orchestrates `upgrade --dry-run` → an agent semantic-conflict
review → an owner confirmation gate → the real `upgrade`. The semantic
review is the agent's own LLM judgment — the installer never calls a
model: for each drifted file and each owner-authored local addition the
agent assesses whether it conflicts with the incoming common-layer
changes and emits an advisory — best-effort, never blocking. The
`update-reminder` hook points the owner at `/upgrade`. A bare
`governance-core upgrade` still works for a manual upgrade; it just skips
the agent-review layer.
