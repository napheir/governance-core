---
id: P-0094
agent: core
status: implemented
created: 2026-06-02
approved_at: 2026-06-02
implemented_in: b73cc8c
implemented_at: 2026-06-02
owner: core
---

# Proposal P-0094: EOL-normalize installer manifest baseline + drift-check (kill CRLF false drift)

## Trigger

Curation of candidate issue gc #27 (`mechanism`, from trade-agent). User
directive: "curate 这两个 candidate". The candidate proposes a code change to
`governance_core/installer.py` drift detection — a package-source capability /
behavior change that ships to every consumer via `upgrade`, so proposal
governance applies (Art.11 single authoritative source; capability add via
`/curate-candidate` step 8 → `/proposal`).

## Scope

`governance_core/installer.py` only:

- Add `_content_sha256(path: Path) -> str` — SHA-256 of a file's content with
  line endings normalized to LF (`\r\n`/`\r` -> `\n` before hashing).
- Use it at the two drift hash-sites so baseline and drift-check agree and are
  EOL-insensitive:
  - `_write_installed_manifest`: `baseline_sha256` (currently
    `hashlib.sha256(dest_path.read_bytes())`).
  - `_capture_drift`: `current` (currently `hashlib.sha256(path.read_bytes())`).
- Add a unit test (new `governance_core/tools/test_installer_drift_eol.py`)
  covering the candidate's test plan: CRLF no-op, genuine-edit-still-caught,
  lone-CR, baseline/drift symmetry.
- Version bump (ships to consumers).

## Non-Goals

- No change to how files are *materialized* (written) — only how they are
  *hashed for comparison*.
- No retroactive manifest migration: the first `upgrade` after this ships may
  reflag a CRLF file once (old raw baseline vs new normalized current), then
  re-records normalized baselines; that single transitional pass is harmless and
  not worth special-casing.
- Binary-file handling: the manifest only covers install-managed text (hooks
  `.py`, tools `.py`, commands/clauses `.md`); unconditional LF-normalization
  over manifest entries is safe. A text-sniff gate is noted but not added.
- Does NOT fix stale-manifest false drift after a `/sync-repos` merge — that is
  a distinct cause (version skew, not EOL) handled by P-0095.

## Guardrails

edit-write-guard (installer.py is package source, not a protected constitution
file — allowed); boundary-guard (all edits in-repo). No command-guard /
sensitive-data-guard surface. Wheel-isolation check confirms no autonomy-layer
leak (Art.11.4).

## Phases

### Phase 0: Governance bootstrap

- Deliverables: this proposal (P-0094) created + approved by explicit user
  curate directive.
- Validation: user directive "curate 这两个 candidate" / "Promote" recorded as
  approval signal.
- Exit criteria: status approved.

### Phase 1: Implement EOL-normalized hashing

- Deliverables: `_content_sha256` helper + both hash-sites switched + new unit
  test + version bump + ledger `promoted` record for gc #27 + issue #27 closed
  with outcome comment.
- Validation: full `tools/test_*.py` suite green; `governance-core upgrade
  --project-root .` + `doctor` exit 0; wheel-isolation (top-level only
  `governance_core*`, no `maintainer/` leak); new test red before fix / green
  after.
- Exit criteria: committed referencing P-0094; tests green; issue closed.

## Approval Criteria

- The fix maps to current source (verified: installer.py:329-330 baseline,
  installer.py:375 drift-check both use raw `read_bytes()`).
- Both hash-sites use the SAME helper (asymmetry would reintroduce the mismatch).
- A genuine (non-EOL) content edit is still detected as drift.

## Validation Plan

1. New unit test red before fix, green after (CRLF no-op; genuine edit caught;
   lone CR; symmetry).
2. `python -m pytest tools/ -q` from repo root — full suite green.
3. `governance-core upgrade --project-root .` then `governance-core doctor` → 0.
   (Hub cannot reproduce the *symptom* — its autonomy layer is gitignored, never
   re-checked-out by git — so end-to-end drift validation is consumer-only; unit
   test is the dogfood-level proof.)
4. `python -m build --wheel`; assert wheel top-level is only `governance_core*`
   (+ dist-info), `maintainer/` absent.

## Rollback / Recovery

Revert the installer.py change (single commit) — drift detection returns to
raw-byte hashing. No data migration to undo; manifests re-record on next upgrade.

## Risks

- **Low — transitional reflag.** First post-ship upgrade may reflag CRLF files
  once. Mitigation: documented, harmless, self-heals on the same run.
- **Low — binary in manifest.** If a binary were ever manifest-tracked, blind
  normalization could over-normalize. Mitigation: manifest is text-only today;
  text-sniff gate noted as a future guard.
- **Low — hub can't dogfood the symptom.** The fix is unit-tested; the
  end-to-end drift reduction is verifiable only on a git-tracking consumer.

## State Log

- 2026-06-02: draft created by core agent (P-0094)
- 2026-06-02: draft → pending (submit for review)
- 2026-06-02: pending → approved (user directive: 'curate 这两个 candidate' (explicit implement order))
- 2026-06-02: approved → implemented
