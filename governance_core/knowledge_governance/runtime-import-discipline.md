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
| `prompt-context-router` | yes (`discovery.tracker`, P-0092) | guards + fails open (UserPromptSubmit, advisory) | OK ✅ |
| `auth-guard` | **no** (vendored `_gc_auth`, P-0082) | fails closed, PreToolUse `*` | self-contained ✅ |

`auth-guard` must fail closed (no valid package ⇒ no capabilities is the
*point*), so it cannot fail open on an import error. **P-0082** made it
self-contained: the installer vendors `governance_core/auth/` (the `codec` +
`_ed25519` + `revocation` chain + `pubkey.json`) to `.claude/hooks/_gc_auth/`
and the hook imports that copy via `sys.path` — the same model as
`proposal-classify-fast` vendoring `_classify_match`, scaled to a package. The
auth subpackage was converted to relative imports so the one source works both
as `governance_core.auth` (package use) and as the vendored `_gc_auth`. No
importer remains in violation.

## 4. Enforcement

`governance_core/runtime_import_audit.py` is the single source of truth:

- `FAIL_OPEN_GC_IMPORTERS` — the verified fail-open importers (allowed).
- `GC_IMPORT_EXEMPT` — fail-closed importers grandfathered pending a fix.
  **Empty as of P-0082** (auth-guard was vendored); a future fail-closed
  importer would be added here only as an explicit, tracked, temporary entry.
- `check_runtime_import_discipline(hooks_dir, shipped_hook_names)` classifies
  each shipped hook; any importer that is in **neither** set is a *violation*.

`governance-core doctor` calls it and **exits 9** on any unclassified importer,
so a new `governance_core`-importing hook cannot ship without an explicit
decision: make it self-contained, or — after verifying it guards the import and
fails open — add it to `FAIL_OPEN_GC_IMPORTERS`. With the exemption set empty,
discipline is now enforced with no exceptions (the grandfather of P-0081
self-decayed when P-0082 vendored auth-guard).

## 5. Adding a new hook — checklist

1. Does it need `governance_core`? If **no** → self-contained, done.
2. If **yes**: does it fire per-call AND fail closed (block on error)? If so,
   make it self-contained instead (vendor what it needs).
3. Otherwise guard the import in `try/except` with a fail-open `sys.exit(0)`,
   then add it to `FAIL_OPEN_GC_IMPORTERS`. Doctor will flag it until you do.
