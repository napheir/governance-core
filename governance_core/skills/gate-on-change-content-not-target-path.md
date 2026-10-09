---
theme: universal
name: gate-on-change-content-not-target-path
description: "When a governance rule keeps getting bypassed despite an existing hard gate, check whether the gate judges the wrong DIMENSION (target path) before widening its allowlist; build a content-signal layer that matches the change delta, and calibrate it by replaying real commit history rather than intuition."
type: guide
owner: core
tags: [governance, enforcement, hook, pretooluse, pre-commit, false-positive-calibration, delta-matching]
created: 2026-08-20
updated: 2026-10-09
---

# gate-on-change-content-not-target-path

When a governance rule keeps getting bypassed despite an existing hard gate, check whether the gate judges the wrong DIMENSION (target path) before widening its allowlist; build a content-signal layer that matches the change delta, and calibrate it by replaying real commit history rather than intuition.

## Preconditions

1. A hard gate already exists and is documented, yet a real case slipped through
2. You can name the specific bypassing change (file + line), not just the category
3. You have read the existing gate's source to see what it actually keys on

## Workflow

1. Reproduce the miss concretely: find the actual change that slipped (file + line) and read the existing gate's decision input. If the gate reads only tool_input.file_path while the signal lives in the diff, no allowlist entry can ever catch it -- this is a dimension mismatch, not a coverage gap
2. Check ownership of every file you would need to touch (for governance-core consumers: .governance/installed_files.json). If the natural home is a managed file, prefer a NEW project-local layer over an in-place edit: zero upgrade-restore debt, and the whole layer stays extractable for later upstreaming
3. Design the matcher DELTA-ONLY, never whole-file state: Edit -> new_string minus old_string, Write -> content minus current file, pre-commit -> '+' lines of git diff --cached -U0. This is the single biggest false-positive control: retuning an existing call must stay silent, introducing a new one must fire
4. Split signals into ANCHOR categories (fire standalone) and COOCCURRENCE-GATED categories (fire only alongside an anchor). A pattern with high standalone prevalence is usually legitimate on its own and only interesting inside automation
5. Prefer an exact predicate over a fuzzy regex wherever the domain supplies one: 'a name absent from the known set' can take a naive path regex's false positives from dozens to zero on the same history
6. Make clearance un-self-servable: require a real id validated against an authoritative ledger, or a recorded waiver. If the existing gate's own CLI can clear the new gate, you have rebuilt the soft rule you were trying to harden -- key on an explicit discriminator field
7. Calibrate BEFORE shipping by replaying N days of real commits through the matcher; build the replay as a reusable instrument, not a throwaway, so the next signal edit can be measured too
8. Judge every replay hit TP/FP by reading the file. Route each FP class to its OWN switch: a filename-heuristic FP gets a per-category new_file_exempt_globs (content patterns still apply); a whole-subtree FP gets a top-level exempt path glob
9. Add a commit-stage backstop sharing the SAME matcher function, so a Bash/heredoc write that no PreToolUse hook can see is still caught, and the two layers cannot drift apart
10. Fail open on every internal error, log the fail-open to an audit file, and provide an env escape hatch -- an enforcement layer must never be able to lock the repo through its own bug

## Outputs

- signals config (hot-editable, with measured prevalence recorded in a _calibration field)
- shared matcher module used by BOTH the PreToolUse hook and the commit-stage backstop
- clearance CLI + a git-tracked clearance ledger with a contract doc
- replay/calibration instrument
- tests including a regression fixture for the exact case that slipped, asserted in BOTH directions (introducing fires, retuning does not)

## Notes

- Widening the existing allowlist is the tempting move and is usually wrong: if the gate reads paths and the signal is in the diff, no path entry helps
- Exempt the gate's own source files -- they contain every pattern as a literal and would self-match; this is not a hole if those paths are already covered by the path-based gate
- Whole-file prevalence is a strict UPPER bound on delta hits; use it to reject noisy candidate patterns cheaply before writing any code
- Record the measured numbers in the config itself, so the next person editing a pattern sees why it was chosen
- A clearance TTL keeps the record meaning 'this change was coordinated' rather than becoming a permanent per-file exemption
