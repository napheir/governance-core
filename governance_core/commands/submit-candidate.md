---
theme: universal
owner: core
---

# /submit-candidate - Offer a capability to governance-core

Package a skill, hook, or mechanism this project has built into a candidate
envelope and uplink it to governance-core for curation (P-0065). This is the
**active** path — the counterpart to the automatic collection of net-new
`candidate-common` skills and of drift in install-managed files.

## When to use

- The user explicitly asks to contribute / submit a capability upstream.
- A skill / hook / mechanism built here is generic enough that other
  governance-core consumers would benefit from it.

## Preconditions

- The project is authorized and recorded candidate-uplink consent at install
  (P-0065) — `governance-core doctor` exits 0.
- The `gh` CLI is installed and authenticated (the envelope travels as a
  GitHub issue).

## Workflow

1. **Identify the payload** — the file(s) that make up the capability:
   - one skill `.md` → `--kind skill`
   - one hook `.py` → `--kind hook`
   - several files that only make sense together → `--kind mechanism`

2. **Classify the layer**: confirm this is genuinely common-layer using the
   generic-vs-project axis in the `lesson-classification` skill. A
   project-specific capability (`--layer business`) should not be uplinked.

3. **Write a rationale** — one or two sentences on what generic problem the
   capability solves and why it belongs in the common layer.

4. **Preview with `--dry-run`** — build the envelope and preview the issue
   without sending anything:
   ```bash
   python tools/candidate.py submit --kind <kind> --title "<title>" \
     --rationale "<why>" --files "<path1>,<path2>" --dry-run
   ```
   Review the printed issue title and body.

5. **Submit** — drop `--dry-run` to build, scan, and open the issue on the
   governance-core repository:
   ```bash
   python tools/candidate.py submit --kind <kind> --title "<title>" \
     --rationale "<why>" --files "<path1>,<path2>"
   ```

6. **Report to user** — show the envelope path and the created issue URL.

## Notes

- The candidate is uplinked to a **public** repository. The payload is
  scanned for secrets (HIGH + MEDIUM severity) before sending; any hit
  aborts the uplink. Never submit a payload carrying credentials.
- Envelopes are staged under `.governance/candidate-outbox/` (gitignored,
  transient).
- governance-core curates incoming candidate issues (P-0065 Phase 5) —
  acceptance is a maintainer decision, not automatic.
- `python tools/validate_candidate.py <envelope-dir>` validates an
  envelope's format independently.
