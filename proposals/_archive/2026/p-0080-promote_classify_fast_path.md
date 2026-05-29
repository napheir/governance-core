---
id: P-0080
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: cdd64fb
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0080: Promote classify fast-path hard-block cluster (candidates #17 bundle + #13 CLI diff)

## Trigger

The classify fast-path cluster (#12/#13/#14) was held as an incomplete bundle;
trade-agent re-submitted a complete, well-formed bundle as **#17** (8 net-new
payloads) and kept the install-managed `proposal_lib.py` CLI diff on **#13**
(39KB full file, exceeds the issue uplink budget). User chose to promote it.
This adds a **5th-layer machine hard-block** PreToolUse hook to the Art.5.4
classify gate — a security-sensitive enforcement capability shipping to all
consumers → proposal governance applies (as P-0078/P-0079).

## Scope

One phase. **Eight net-new files from #17** + a **pure-add merge from #13** +
**hook registration**. Install destinations:

| Payload (#17) | Destination |
|---|---|
| `proposal-classify-fast.py` (PreToolUse hard-block hook) | `governance_core/hooks/` |
| `_classify_match.py` (gitignore-glob matcher) | `governance_core/tools/` |
| `proposal-classify-paths.json` (high-sensitivity path allowlist) | `governance_core/tools/` |
| `proposal-classify-keywords.json` (structural-change keyword list) | `governance_core/tools/` |
| `test_proposal_classify.py` / `_fast_hook.py` / `_paths.py` (3 tests) | `governance_core/tools/` |
| `proposal-classify-fast-path.md` (reference doc, carrier_class: reference) | `governance_core/knowledge_governance/` |

- **#13 merge** → `governance_core/tools/proposal_lib.py` gains `_cmd_classify` /
  `_classify_quick` + argparse wiring. Verified: `git diff --ignore-cr-at-eol`
  of #13's full payload vs current source = **3 hunks / 158 add / 0 del — pure
  add** (baseline `9cfbbd2…` drifted to `bba8f84…`, but the drift is CRLF noise;
  semantically current == baseline). Apply via `git apply --recount`.
- **Register hook** → add
  `"proposal-classify-fast.py": {"event":"PreToolUse","matcher":"Edit|Write|MultiEdit|NotebookEdit"}`
  to `governance_core/hooks/hooks_manifest.json`; the installer regenerates
  `.claude/settings.local.json` from the manifest (P-0067). `doctor` flags an
  installed hook missing from the manifest, so this entry is mandatory.
- **Version bump** 0.13.0 → 0.14.0 (new hook + configs + CLI subcommand ship in
  the wheel; consumers receive via `upgrade`).

Verified pre-conditions: the new hook is **self-contained — no
`import governance_core`** (grep-confirmed across the whole bundle), honoring the
copy-based runtime invariant (the very invariant issue #3's auth-guard breaks).
Configs are **generic** — `paths.json` globs are governance-core's own structure
(`CLAUDE.md`, `constitution/**`, `contracts/**`, `agent_rules/**`, `.governance/**`,
`.claude/hooks/**`, `INDEX.routing.json`, `proposal_lib.py`, `audit_*.py`,
`settings`), `keywords.json` is generic structural-change triggers — no trade
leakage.

## Non-Goals

- **#14 `sync_infra` ALWAYS_COPY_FILES** multi-clone distribution wiring —
  EXCLUDED per trade-agent's own scope note + single-agent hub topology (no other
  clones to sync to).
- Not re-sending `proposal_lib.py` wholesale — merge the 158-line diff only.
- No change to the existing soft layers (L1 Art.5.4 clause, L2 `/proposal
  classify`, L3 guide, L4 `proposal-classify-reminder.py`) — this adds L5.
- No genericization needed (configs already generic, unlike #11).

## Guardrails

- **edit-write-guard**: all targets are package source (`governance_core/**`),
  not `CLAUDE.md`/`constitution/*` — not blocked; core owns them.
- **copy-based self-containment** (issue #3 invariant): the new hook carries NO
  `import governance_core` (verified) — it imports stdlib + sibling
  `_classify_match` via `sys.path.insert`. This is the GOOD pattern.
- **doctor / hooks_manifest**: adding the hook REQUIRES the manifest entry or
  doctor flags it — covered in scope.
- **Art.11.4 isolation**: new files all under `governance_core/` — wheel stays
  `governance_core*` only (validate).
- **constitutional-review (Art.4)**: review the merged `proposal_lib.py` +
  configs for `.get(k, default)` config fallback — the config loaders use
  `data["categories"]` / `data["keywords"]` (required-key access, raises on
  missing), not silent defaults; confirm on apply.
- **boundary-guard / sensitive-data-guard**: in-boundary; payloads secret-scanned
  at uplink.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — no constitution / contract / agent_rules change. Adding a hook
  + tools + doc is package-source feature work (the hook ENFORCES Art.5.4 but
  does not amend it).

### Phase 1: Land + register + merge + dogfood + verify + promote

- Deliverables:
  - Place the 8 #17 payloads at the destinations above.
  - `git apply --recount` the #13 `_cmd_classify` merge onto `proposal_lib.py`.
  - Add the `proposal-classify-fast.py` entry to `hooks_manifest.json`.
  - Bump 0.13.0 → 0.14.0.
  - Run full `tools/test_*.py` + the 3 new classify tests.
  - `governance-core upgrade --project-root .` → hook registered in
    `settings.local.json`; `governance-core doctor` exit 0 (hook count +1).
  - **Verify the hard-block end to end** (see Validation Plan).
  - wheel 0.14.0 isolation check.
  - `candidate.py promote` #17 (decision=promoted); close #17/#13/#12/#14.
- Validation: see Validation Plan.
- Exit criteria: tests green incl. the 3 new; hook registered + doctor 0;
  hard-block + escape hatch + fail-open verified; wheel isolated; issues closed.

## Approval Criteria

- Reviewer accepts **activating a hard-block PreToolUse hook in the hub's own
  session** — with the understanding that (a) it only gates root/autonomy
  governance paths, NOT `governance_core/**` package source (the self-hosted
  nuance: globs are autonomy-relative, so core's package-source work is
  unaffected); (b) `CLAUDE_CLASSIFY_FAST_DISABLE=1` is an immediate kill switch;
  (c) the hook is fail-open.
- Reviewer confirms the bundle is generic + self-contained (verified) and the
  `proposal_lib.py` merge is pure-add (verified).

## Validation Plan

- Apply: `git apply --recount` the proposal_lib merge (dry `--check` first).
- `python -m py_compile` the hook + matcher + merged proposal_lib.py.
- Full `tools/test_*.py` + the 3 new tests (`test_proposal_classify*.py`) green.
- `python tools/proposal_lib.py classify "<edit governance path>"` returns
  PROPOSAL_REQUIRED via the fast path; a benign description returns NO_PROPOSAL.
- `governance-core upgrade --project-root .` exit 0;
  `.claude/settings.local.json` registers `proposal-classify-fast.py` on
  PreToolUse; `governance-core doctor` exit 0.
- **Hard-block behavior** (dogfood, manual): with the hook active and no classify
  entry this session, an Edit to an allowlisted root path (e.g. a scratch file
  matching a glob) is blocked (exit 2); `CLAUDE_CLASSIFY_FAST_DISABLE=1` allows
  it; an induced hook error falls open (exit 0 + error-log line). Confirm an Edit
  to `governance_core/**` is NOT blocked (self-hosted nuance).
- wheel 0.14.0: top-level only `governance_core*`; the hook + configs + tests +
  doc present; `maintainer/` absent.
- `candidate.py review` shows #17 promoted.

## Rollback / Recovery

- **Immediate kill switch**: `CLAUDE_CLASSIFY_FAST_DISABLE=1` disables the hook
  without any code change (set in the launching shell).
- Pre-commit: `git checkout -- <files>` + remove the manifest entry + `upgrade`
  to deregister.
- Post-commit: `git revert <hash>` removes the hook, configs, merge, and manifest
  entry; re-run `upgrade` to drop the registration from `settings.local.json`.
  No state/schema migration — pure code/config revert.

## Risks

- **Hard-block impedes the hub's own session** (low, mitigated): the globs are
  autonomy-relative and exclude `governance_core/**`, so core's package-source
  work is ungated; root/autonomy governance edits are gated but those are exactly
  the edits that should be classified, and `CLAUDE.md`/`constitution/*` are
  already edit-write-guard-blocked. Escape hatch + fail-open bound the blast.
- **Installer mis-wires the new hook** (low): doctor flags a manifest/registration
  mismatch; validated in Phase 1.
- **keywords.json activates the existing reminder hook's matching** (low/benign):
  `proposal-classify-reminder.py` was no-op without the keyword file; now it will
  surface keyword-based reminders. Intended — completes the L4 layer.
- **Hard-block hook = a new injection/lock surface** (low): fail-open guarantees a
  hook bug never freezes the repo; errors are logged to
  `audit/proposal_classify_fast_errors.jsonl`.
- **Version bump** 0.13.0 → 0.14.0.
- **Ceremonial-proposal critique** (accepted): single-agent self-review; weight
  justified by security-sensitivity + all-consumer blast radius + curation record.

## State Log

- 2026-05-29: draft created by core agent (P-0080)
- 2026-05-29: draft → pending (submit classify fast-path hard-block cluster (#17+#13) for maintainer review)
- 2026-05-29: pending → approved (user signal: 批准)
- 2026-05-29: approved → implemented
