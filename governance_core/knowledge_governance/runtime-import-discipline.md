---
title: Runtime Import Discipline (P-0081)
status: active
created: 2026-05-29
updated: 2026-05-29
owner: core
carrier_class: reference
tags: [governance, hooks, runtime, import, self-containment, fail-open, p-0081]
related:
  - knowledge/governance/scope-enforcement-mechanism.md
  - knowledge/governance/resource-layer-hardening.md
---

# Runtime Import Discipline

How a copy-installed hook may (and may not) depend on the `governance_core`
package at runtime. Rooted in issue #3; established by P-0081; enforced by
`governance-core doctor` via `governance_core/runtime_import_audit.py`.

## 1. The invariant

> A shipped hook that imports `governance_core` at runtime **MUST guard the
> import and fail open** (`sys.exit(0)` — degrade, never obstruct) if the
> import fails. A hook that must **fail closed** (a security gate that denies
> the tool call on any error) **MUST be self-contained** — it must NOT import
> `governance_core` at all.

Equivalently: `imports_governance_core ⟹ fails_open`. The contrapositive is the
teeth — `fails_closed ⟹ self_contained`.

## 2. Why

Copy-installed hooks are standalone snapshots; the package is the source. Most
hooks legitimately import `governance_core` for a capability (the candidate
pipeline, the skill tracker, the secret scanner) — that is fine **as long as a
missing or broken package degrades gracefully**, because those hooks are
advisory or fire infrequently.

The danger is a hook that (a) fires on **every** tool call and (b) **fails
closed**. For such a hook an *import* failure — a broken or uninstalled
package, an infrastructure fault — is **indistinguishable from a real denial**.
It would block every tool call and **freeze the whole session**, with no
graceful path. A self-contained gate has no import that can fail, so it can
fail closed on real auth/scope problems *only*.

This is why every per-tool-call guard (`command-guard`, `scope-guard`,
`edit-write-guard`, `constitutional-review`, `data-source-guard`,
`direction-guard`, `merge-audit`, `repo-health`, `proposal-classify-fast`) is
**self-contained**.

## 3. Current classification (0.14.0)

| Hook | Imports `governance_core`? | Failure mode | Status |
|---|---|---|---|
| the 9 per-call guards above | no | n/a | self-contained ✅ |
| `sensitive-data-guard` | yes (`sensitive_scan`) | guards + **fails open** | OK ✅ |
| `candidate-reminder` / `renewal-reminder` / `update-reminder` | yes | guards + fails open (SessionStart, advisory) | OK ✅ |
| `skill-usage-tracker` | yes (`discovery.tracker`) | guards + fails open (PostToolUse) | OK ✅ |
| **`auth-guard`** | **yes** (`auth.codec` / `revocation`) | **fails closed**, PreToolUse `*` | **VIOLATION** ❌ |

`auth-guard` is the sole violator: it must fail closed (no valid package ⇒ no
capabilities is the *point*), so it cannot fail open on an import error — the
only correct fix is to make it **self-contained**. That refactor (vendor the
`codec` + `_ed25519` + `revocation` chain + `pubkey.json` as install-copied
hook helpers, the way `proposal-classify-fast` vendors `_classify_match`) is
tracked as **P-0082**.

## 4. Enforcement

`governance_core/runtime_import_audit.py` is the single source of truth:

- `FAIL_OPEN_GC_IMPORTERS` — the verified fail-open importers (allowed).
- `GC_IMPORT_EXEMPT` — fail-closed importers grandfathered pending a fix
  (currently `{auth-guard.py}`; **remove when P-0082 lands**).
- `check_runtime_import_discipline(hooks_dir, shipped_hook_names)` classifies
  each shipped hook; any importer that is in **neither** set is a *violation*.

`governance-core doctor` calls it and **exits 9** on any unclassified importer,
so a new `governance_core`-importing hook cannot ship without an explicit
decision: make it self-contained, or — after verifying it guards the import and
fails open — add it to `FAIL_OPEN_GC_IMPORTERS`. `auth-guard` is reported as a
tracked exception and does not fail doctor (grandfather pattern, mirroring
P-0075's prune-exempt: enforce going forward, self-decay when the violator is
fixed).

## 5. Adding a new hook — checklist

1. Does it need `governance_core`? If **no** → self-contained, done.
2. If **yes**: does it fire per-call AND fail closed (block on error)? If so,
   make it self-contained instead (vendor what it needs).
3. Otherwise guard the import in `try/except` with a fail-open `sys.exit(0)`,
   then add it to `FAIL_OPEN_GC_IMPORTERS`. Doctor will flag it until you do.
