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

Skill usage is a three-layer **funnel** (P-0092, gc #25): a skill reaches the
agent by being **Surfaced** (named in the SessionStart menu), **Triggered**
(its router keyword hits and the body head is injected), or **Loaded** (full
body pulled). `use_count` only counts Loaded, so learned/guide skills designed
to act from the summary or the injected head score 0 even when applied. The
tracker now records all three; read the funnel with:

```pwsh
python -m governance_core.discovery.registry --funnel
```

It classifies each learned/guide skill as a **retire** candidate (surfaced,
never triggered or loaded), a **slim** candidate (triggered, never loaded — the
head suffices), or a star. The counters are diagnostic only — they do not feed
`weighted_scores` or change injection ordering.

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

To correct a mistaken revocation (P-0074), `revoke_consumer.py --unrevoke
<id>` removes that one consumer from the feed, re-signs it, and marks the
registry entry `active` again -- other revoked entries are untouched.
Revocation is still intended as durable; `--unrevoke` is a maintainer
correction, not a routine on/off toggle.

### Lease-renewal visibility (P-0074)

Schema-2 codes are 365-day leases; renewal means re-issuing before
`expiry`. To see which consumers are due:

```pwsh
python maintainer/renewal_status.py
python maintainer/renewal_status.py --threshold-days 45
```

It scans `consumer_registry.json`, lists every active consumer ordered by
days left on its lease, and flags `[RENEW]` for any within the renewal
window (default 30 days) and `[LAPSED]` for any already expired. The same
view surfaces unprompted: the `renewal-reminder` SessionStart hook prints a
`[Lease renewal]` banner whenever a lease is within the window. That hook
is **hub-side** -- it reads `maintainer/consumer_registry.json`, a file
only this repo carries, so a consumer project that merely installed the
package stays silent (the opposite of `candidate-reminder` /
`update-reminder`, which are consumer-side).

This is visibility only. Renewal stays a deliberate act -- re-run
`issue_auth_code.py --consumer-id <id>` for the flagged consumer. There is
no auto-renewal: a signed auto-renewal feed was deliberately left out of
P-0074 (it trades against P-0071's lease-expiry-as-backstop) for a
separate proposal.

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

The baseline and the drift-check hash **EOL-normalized** content (`installer.
_content_sha256` maps `\r\n`/`\r` -> `\n` before hashing), at both the
`_write_installed_manifest` baseline and the `_capture_drift` current site
(P-0094, gc #27). Without this, a consumer on `core.autocrlf=true` (the Windows
default) re-checks-out git-tracked install-managed text as CRLF and every file
false-drifts against its LF baseline. Note: this hub cannot reproduce that
symptom — its autonomy layer is gitignored, so git never re-checks-it-out — so
the fix is unit-tested (`tools/test_installer_drift_eol.py`) and verified by a
post-re-baseline `upgrade --dry-run` reporting 0 drift. The first `upgrade`
after upgrading to 0.24.0 may reflag a CRLF file once (old raw baseline vs new
normalized current), then re-records normalized baselines — harmless.

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

### Released-to-business: STALE_PRUNE_EXEMPT (P-0075, gc #24)

> Release cohorts so far: **P-0075** (0.7.0 — design residue: component-catalog
> / design-principles / design-system-owner), **gc #24 / P-0091** (knowledge
> RENDERING tools released to consumer ownership: `build_knowledge_dashboard.py`
> / `build_autogen_blocks.py` / `.claude/commands/dashboard.md` — gc owns the
> knowledge contracts/validators/taxonomy, not how a project renders).

When the package source drops a file that downstream consumers may already
be relying on as business content, naive prune would silently delete it
(drift-capture only fires when the file was *edited*, not when it was
referenced as-is). `installer._prune_stale` therefore checks a hard-coded
`STALE_PRUNE_EXEMPT` set: a path in the set is logged as `[prune] released
to business ownership: <path>` and **not** deleted. The new manifest
naturally omits the path (no source → not in `installed`), so the exemption
fires **once** — on the upgrade that crosses the dropping version — and
subsequent prunes never look at the path again.

Mechanic for the maintainer adding a removal:

1. Delete the file(s) from the package source as usual.
2. Add their installed-layer paths to `STALE_PRUNE_EXEMPT` in
   `governance_core/installer.py` *in the same change* — without this, every
   consumer that ever installed the previous version loses the file on
   upgrade.
3. Add regression cases in `governance_core/tools/test_upgrade_dry_run.py`
   (`_prune_exempt_cases`) covering: each new exempt path survives prune,
   and a non-exempt control path is still pruned.
4. After all known consumers have crossed the dropping version, a future
   major-version cleanup may remove the entries (the manifest-diff
   mechanism alone is then sufficient).

`STALE_PRUNE_EXEMPT` is intentionally narrow: it covers paths whose
*ownership transferred* at a version line. Paths that genuinely no longer
make sense (e.g. an old hook replaced by a new one) should just be pruned.

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

### Sweep ledger self-heal (P-0076 Phase 1)

The dedup ledger is consumer-side and gitignored — a wiped clone, a
manual `rm -rf .governance/`, or a failed write all leave the consumer
with a learned skill that was already uplinked but no record proving
so. The next sweep would treat every existing envelope as net-new and
flood the hub with duplicates.

To prevent that, `cmd_sweep` self-heals at the start of every run when
the ledger is empty + the outbox is non-empty + `gh` is available:
`ledger.discover_uplinked_from_hub(origin, repo)` queries `gh issue
list --state all --search "[candidate] (from <origin>)"`, parses each
issue body's `### payload/<name>` fenced block, rehashes via
`_hash_payload`, and writes the rebuilt entries into `_uplinked.json`.
The healthy consumer (ledger intact) never triggers it.

Recovery is fail-safe: any `gh` failure, JSON-decode error, or
malformed issue body logs at INFO and returns empty so the existing
sweep behavior takes over — recovery never blocks wrap-up.

### Drift candidates carry diffs, not full files (P-0077)

A drift envelope is captured when an install-managed file has been
locally edited — `installer._capture_drift` packages the consumer's
**current** file bytes for transport. Pre-0.9.0, the entire current
file rode in the issue body; for files in the 40+ KB range this hit
two failures simultaneously:

- Windows `CreateProcessW` cmdline cap (~32K UNICODE_STRING) — Python
  surfaces this as a misleading `FileNotFoundError` ("`gh` CLI not
  found").
- The hub-side `ISSUE_BODY_LIMIT` (60K chars) — a 143KB drifted file
  cannot even build a candidate issue.

The hub already ships the upstream baseline; reshipping the full
current bytes is wasted transport. Starting with 0.9.0, when an
envelope has `drift_target` + `baseline_sha256` and the baseline can
be located via `installer._pkg_source_path`, `uplink.build_issue`
emits a unified diff under `### drift diff (unified, against
baseline)` plus a metadata header:

```
- drift_target: `tools/proposal_lib.py`
- baseline_sha256: `…`
- payload_form: diff
- payload_sha256: `…`
```

The `payload_sha256` field carries the consumer-side digest the ledger
would have recorded (basename + null + bytes hash); the hub's
`parse_payload_from_issue_body` short-circuits on `payload_form: diff`
and takes this sha directly, so `discover_uplinked_from_hub` (P-0076
Phase 1) and `maintainer/reject_candidate.py` (P-0076 Phase 2) both
keep working without rehashing.

Fallback: if `_pkg_source_path` cannot resolve the drift target
(unfamiliar autonomy path, missing source), `build_issue` reverts to
the legacy full-payload form. Net-new candidates (no `drift_target`)
always use the full-payload form so ledger rehash still works.

The `gh` invocation also switches to `--body-file <tempfile>`, which
sidesteps the Windows cmdline cap entirely for any candidate body size
that fits the 60K hub limit. Linux/macOS behavior is unchanged.

### Hub setup: required labels

Fresh hub repos need three `kind/*` labels plus the umbrella
`candidate` label, or `gh issue create --label kind/X` fails with
"label not found":

```bash
gh label create "candidate"      --color D4C5F9 -R <hub-repo>
gh label create "kind/skill"     --color C5DEF5 -R <hub-repo>
gh label create "kind/hook"      --color C5DEF5 -R <hub-repo>
gh label create "kind/mechanism" --color C5DEF5 -R <hub-repo>
```

`uplink.uplink_envelope` recognizes the "label not found" stderr
pattern and prints the same `gh label create` block as a hint.

### Reject feedback registry (P-0076 Phase 2)

A consumer can keep editing a rejected skill — payload digest changes —
and the dedup ledger considers each variant net-new, so sweep keeps
re-uplinking the same fundamentally-business-layer skill under fresh
ids. P-0076 Phase 2 closes that gap with a hub→consumer feedback
channel.

The hub ships `governance_core/candidates/rejected_registry.json`
(committed in package source, included in every wheel). Each entry
records:

```json
{
  "rejected_at": "2026-05-26",
  "skill_name": "p4-scenario-fixture-construction",
  "payload_sha256": "ee67474d..." or null,
  "block_by_name": false,
  "origin": "trade-agent",
  "issue_urls": [...],
  "reason": "Business-layer content. ...",
  "advice": "Keep as a local learned skill. Remove `layer: candidate-common`..."
}
```

Consumer-side `cmd_sweep` consults the registry via
`governance_core.candidates.rejected.is_rejected(name, sha)`:

| Match           | block_by_name | Action                                                                                  |
|-----------------|---------------|-----------------------------------------------------------------------------------------|
| `exact` (sha=)  | (irrelevant)  | **Block** uplink. Print structured `[candidate] sweep: SKIPPED ...` advisory on stdout. |
| `name` (sha≠)   | `true`        | **Block** uplink. (Used for pre-0.8.0 backfill where sha was unrecoverable.)             |
| `name` (sha≠)   | `false`       | Warn on stderr (`[candidate] sweep: NOTE ...`) and **allow** uplink so the hub re-evaluates. |
| no match        | —             | Normal collect/uplink path.                                                              |

The advisory is consumer-visible: it carries the reason text and
advice text the maintainer wrote, plus issue URLs. The mechanism is
advisory only: nothing in this module modifies a consumer's skill
files. The aim is owner awareness, not control.

`candidate-reminder.py` SessionStart hook (Phase 2 extension) also
cross-checks pending skills against the registry and adds a
`WARNING: N of these were previously REJECTED by the hub (...)` line
to the startup banner when applicable — surfacing the situation
without waiting for the next wrap-up.

Consumers learn of new rejections via the existing `update-reminder`
flow (P-0073): a maintainer ships a new wheel → consumer's
SessionStart banner prompts an upgrade within ~12h of the release.

## 13. Maintainer reject workflow (P-0076 Phase 2)

When an uplinked candidate is business-layer content (or otherwise
unfit), package the reject into a durable record using:

```pwsh
python maintainer/reject_candidate.py \
    --issue <N> \
    --reason "Why this is not a common capability ..." \
    --advice "What the consumer should do ..." \
    [--also-close]
```

The tool:

1. Fetches the issue body via `gh issue view`.
2. Parses the embedded `### payload/<name>` fenced block using the
   shared parser from P-0076 Phase 1.
3. Computes the payload's SHA-256 over the bytes the issue carries.
4. Detects whether the issue was created by **pre-0.8.0** uplink
   (which had stripped trailing whitespace, so the digest is
   approximate). Pre-0.8.0 → sets `payload_sha256: null` and
   `block_by_name: true` so the registry still blocks regardless of
   the consumer's exact bytes. Post-0.8.0 → records the precise sha.
5. Appends (or merges into an existing same-name entry) in
   `governance_core/candidates/rejected_registry.json`.
6. With `--also-close`, posts the reason+advice as a comment and
   closes the issue as `not planned`.

**Writing a good reason+advice pair**:

- **reason**: name the structural problem, not just the symptom.
  "Business-layer content (HK options strangle50 / o2_score
  boundaries / signals path)" tells the consumer's owner what to look
  for. "Doesn't fit" doesn't.
- **advice**: be actionable. "Remove `layer: candidate-common`" /
  "Rename to `<x>` if you want to retry" / "Delete if no longer used"
  is concrete; "consider whether this is generic" is not.

The registry is shipped in the next wheel; consumers pick it up at
their next `governance-core upgrade`. To remove a rejection later
(e.g. you decide a skill is in fact common after all), edit the JSON
directly and bump the version — there is no `unreject` workflow on
purpose, to keep the policy auditable.

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

**Curating a drift `mechanism` candidate.** `promote` does not auto-place a
`mechanism` — and a P-0077 drift candidate targets a file governance-core
itself ships, so verify the payload still applies before placing it by hand.
Compare the candidate's `baseline_sha256` against the current package source
(`sha256sum governance_core/<path>`): equal → the payload applies cleanly;
drifted → use `git apply -p1 --recount`, which relocates the hunks by context
(a plain `git apply` fails on the stale line numbers). Apply to
`governance_core/` only — never the autonomy-layer copy (Art.11.2) — run the
test suite, `governance-core upgrade --project-root .` to dogfood, then
`candidate.py promote ... --decision promoted` to record the decision and
close the issue. P-0078 (the HTML profile cluster, issues #16 + #10) is the
worked example: #10's baseline matched (pure-add), #16's had drifted but
`--recount` relocated all 7 hunks cleanly.

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

### Upgrade drift-risk pre-pass (P-0093, gc #22)

`tools/upgrade_review.py` is a deterministic, read-only **pre-pass** a consumer
can run (manually or from a scheduled routine) to triage an available upgrade
before applying it. It runs `upgrade --dry-run`, mechanically classifies the
result, writes a report under `audit/upgrade_review/` (gitignored), and **never
applies** (exit 0 always):

- **NONE** — already up to date.
- **GREEN** — new version, zero drift, no minor-line crossing — ready.
- **YELLOW** — drift (local edits would be reverted), or a minor-line crossing.
- **RED** — drift on a *protected* local fix, or a minor-line crossing that also
  carries drift.

A consumer lists files it deliberately keeps as local drift in
`audit/upgrade_review/protected_drift.json` (`{"paths": [...]}`); a drift on one
of those forces **RED**, because the upgrade would silently revert a fix the
consumer means to keep. The `update-reminder` hook wires this in: when it
already detects a newer version it runs the pre-pass best-effort (25s timeout)
and appends the verdict to the banner, falling back to the plain banner on any
error. The hub itself never runs it (the editable install early-exits). Apply
always stays a human action via `/upgrade`.
