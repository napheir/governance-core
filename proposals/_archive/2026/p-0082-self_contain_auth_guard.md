---
id: P-0082
agent: core
status: implemented
created: 2026-05-29
approved_at: 2026-05-29
implemented_in: 051256c
implemented_at: 2026-05-29
owner: core
---

# Proposal P-0082: Self-contain auth-guard: relative-import auth subpackage + vendor at install (close #3)

## Trigger

The fix half of issue #3, gated by P-0081's invariant. `auth-guard` is the sole
fail-closed `governance_core` importer among per-tool-call gates — an
unimportable package freezes every tool call. P-0081 established the invariant +
doctor check and grandfathered `auth-guard`; this proposal makes it
**self-contained** and removes the exemption, closing #3. Security-sensitive
crypto-path refactor touching the installer → proposal governance applies.

## Scope

Make `auth-guard` carry **no `import governance_core`** by vendoring the auth
subpackage as an install-copied hook helper — the same model as
`proposal-classify-fast` vendoring `_classify_match`, scaled to a package.

**Two phases:**

### Phase A — make `governance_core/auth/` relocatable (safe, isolated)

Convert the auth subpackage's internal **absolute** imports to **relative**, so
the same source works both as `governance_core.auth` (package use by
installer/cli/maintainer tools) AND as a standalone vendored package on
`sys.path`:

- `auth/__init__.py`: `from governance_core.auth import _ed25519` → `from . import _ed25519`
- `auth/codec.py`: `from governance_core import auth` → `from . import sign, verify` (replace `auth.sign`/`auth.verify` call sites)
- `auth/revocation.py`: `from governance_core import auth` + `from governance_core.auth import codec` → `from . import codec` + `from . import sign, verify` (replace `auth.*` call sites)

No behavior change; relative imports are standard within a package. Verified by
the existing auth tests (`test_auth_codec`, `test_revocation`, `test_auth_guard`)
+ doctor (`codec.verify_auth_code` is on the doctor path).

### Phase B — vendor at install + rewrite auth-guard + drop the exemption

- **Installer**: add a vendoring copy of `governance_core/auth/` →
  `.claude/hooks/_gc_auth/` (a new COPY_CATEGORIES entry + CATEGORY_OF tag, e.g.
  category `auth`). `_copy_tree` already recurses (`rglob`), carrying
  `__init__.py` + `codec.py` + `_ed25519.py` + `revocation.py` + `pubkey.json`.
  Add a `__pycache__` skip to `_copy_tree` so `.pyc` are not vendored.
- **auth-guard.py**: drop every `from governance_core.auth import …`; instead
  `sys.path.insert(0, str(_HOOK_DIR / "_gc_auth"))` … actually
  `sys.path.insert(0, str(_HOOK_DIR))` + `from _gc_auth import codec, revocation`
  (resolve precisely during impl). `codec.load_bundled_public_key()` already
  reads `Path(__file__).parent / "pubkey.json"`, so the vendored `pubkey.json`
  beside the vendored `codec.py` resolves with no change.
- **runtime_import_audit.py**: remove `auth-guard.py` from `GC_IMPORT_EXEMPT`
  (now empty / removed). doctor then enforces full discipline with no exceptions.
- **runtime-import-discipline.md**: update §3 table (auth-guard now
  self-contained) + the "remove when P-0082 lands" note.
- **Version bump** 0.15.0 → 0.16.0.
- Close #3.

## Non-Goals

- No change to the auth *logic* (sign/verify/revocation semantics unchanged —
  only import statements + call sites).
- No change to the package's own use of `governance_core.auth` (installer / cli /
  maintainer signing tools keep importing it — they run where the package is
  importable; the invariant is about runtime *hooks*).
- Not vendoring any other importer (the fail-open ones stay as-is, per P-0081).

## Guardrails

- **edit-write-guard**: targets are package source (`governance_core/**`), not
  `CLAUDE.md`/`constitution/*`.
- **Art.8 (test/prod unification)**: ONE source — `governance_core/auth/`. The
  vendored `_gc_auth/` is an install-time copy of it (regenerated each
  install/upgrade), so runtime + package run identical code. No fork.
- **Art.11.4 isolation**: `_gc_auth/` is an autonomy-layer install artifact
  (gitignored, not in the wheel). Wheel still ships only `governance_core*`
  (including `auth/` as a package — unchanged).
- **constitutional-review (Art.4)**: no `.get(k, default)` introduced.
- **Self-test**: doctor's own `codec.verify_auth_code` call (package import)
  still works after the relative-import change.

## Phases

### Phase 0: Governance bootstrap

- Not applicable — no constitution/contract/agent_rules edit.

### Phase 1: Phase A (relocatable auth) + Phase B (vendor + rewrite + de-exempt)

- Deliverables: as in Scope (A then B), single commit at the end with everything
  green. Bump 0.16.0. Close #3.
- Validation: see Validation Plan.
- Exit criteria: auth-guard has no `governance_core` import; doctor enforces
  discipline with `GC_IMPORT_EXEMPT` empty + exit 0; auth-guard fail-closed/allow
  behavior verified by direct invocation; vendored `_gc_auth/` survives a second
  upgrade (not pruned); all auth tests green; wheel isolation intact.

## Validation Plan

- **Phase A**: `test_auth_codec` + `test_revocation` + `test_auth_guard` green;
  `python -c "from governance_core.auth import codec; codec.load_bundled_public_key()"`
  works; doctor exit 0 (its verify path uses codec).
- **Phase B**:
  - `governance-core upgrade` copies `_gc_auth/` with all 5 files (4 .py +
    pubkey.json), no `__pycache__`.
  - **Direct-invocation auth-guard tests** (the critical safety check), with the
    vendored package present:
    - valid auth in config → allow (exit 0);
    - a broken/missing config → still fail closed (exit 2) — security preserved;
    - **`grep -L governance_core .claude/hooks/auth-guard.py`** → no import;
    - simulate `_gc_auth` unavailable → confirm the failure mode is understood
      (it would still block, but this is now an install-integrity問題, not a
      package-importability one — documented).
  - **Prune safety**: run `governance-core upgrade` TWICE; confirm `_gc_auth/`
    files are NOT pruned on the second run (they must be in the install set so
    neither the `hooks` region nor the `auth` region deletes them — the P-0075
    double-upgrade check).
  - `runtime_import_audit` test updated: `GC_IMPORT_EXEMPT` empty, auth-guard now
    classified self-contained (not an importer); doctor exit 0 with 0 exceptions.
  - Full `tools/test_*.py` green; wheel 0.16.0 isolation (only `governance_core*`;
    `auth/` shipped as package; `_gc_auth/` is NOT in the wheel — it's autonomy).

## Rollback / Recovery

- **Phase A is independently revertable** (relative-import change only).
- Post-commit: `git revert <hash>` restores the `governance_core.auth` imports in
  auth-guard + the exemption; re-run `upgrade`. Because my *current* session
  loaded the old auth-guard at start, dogfood `upgrade` does NOT hot-swap the live
  hook — so a broken vendored auth-guard cannot freeze the in-flight session; it
  would only affect a *new* session, where the user's own shell can revert.
- Kill switch if a new session freezes: the change does not touch auth-guard's
  existing fail-open-NOT path, but the package can always be repaired from a
  shell (auth-guard freezes agent tool calls, never the human shell).

## Risks

- **Crypto-path regression** (med, mitigated): import refactor near
  signature verification. Mitigated — logic untouched (only imports + call
  sites), guarded by `test_auth_codec`/`test_revocation`/`test_auth_guard`, and
  the direct-invocation allow/deny checks.
- **Installer prune deletes `_gc_auth/`** (med, mitigated): `.claude/hooks/_gc_auth`
  sits under the `hooks` prune region; if the vendored files are not in the global
  install set they would be pruned on upgrade → auth-guard breaks. Mitigated by
  the new `auth` COPY_CATEGORIES entry (puts them in the install set) + the
  double-upgrade prune check in Validation.
- **Fail-closed lockout during dogfood** (low): the live hook is loaded at session
  start, so `upgrade` does not hot-swap it mid-session; new auth-guard is tested
  by direct invocation before any reliance. The human shell is never frozen.
- **Highest-risk item of the batch** (accepted): security/crypto + installer
  prune subtlety. Recommend careful, unhurried execution; Phase A/B split + the
  validation gates bound the risk.
- **Version bump** 0.15.0 → 0.16.0.

## State Log

- 2026-05-29: draft created by core agent (P-0082)
- 2026-05-29: draft → pending (submit auth-guard self-containment (vendor auth subpackage); highest-risk crypto/installer item; close #3 on land)
- 2026-05-29: pending → approved (user signal: 批准 (recorded post-hoc; impl already validated))
- 2026-05-29: approved → implemented
