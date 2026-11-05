---
name: installer-writes-into-consumer-owned-file
description: "When an installer or upgrade tool must put content into a file the consumer also owns and edits (.gitignore, .gitattributes, settings.json, a CLAUDE.md section): own only a minimal region, preserve every other byte, refuse to guess at damaged or owner-changed content, stay idempotent, and keep the file out of the install manifest."
type: learned
layer: candidate-common
tags: [installer, upgrade, consumer-owned, idempotent, gitignore, settings-json, manifest]
created: 2026-11-05
updated: 2026-11-05
---

# installer-writes-into-consumer-owned-file

When an installer or upgrade tool must put content into a file the consumer also owns and edits (.gitignore, .gitattributes, settings.json, a CLAUDE.md section): own only a minimal region, preserve every other byte, refuse to guess at damaged or owner-changed content, stay idempotent, and keep the file out of the install manifest.

## Preconditions

1. The target file is consumer-owned: the project may already have it, edit it, or commit it
2. The tool needs only a bounded piece of it (a few lines, one key), not the whole file

## Workflow

1. Pick the smallest ownable unit: a marker-delimited block for line files (.gitignore), a single key for JSON (settings.json projectRoot); never rewrite the whole file
2. Read raw (open with newline='') and detect the file's own line ending; write the block with that ending and write back with newline='' so CRLF files stay CRLF
3. Replace the block in place between the begin and end markers; if absent, append it after a blank line; leave every byte outside the markers untouched
4. Refuse on damage: a begin marker without an end marker, unparseable JSON, or a non-object JSON root means log a warning and leave the file unchanged rather than guessing
5. Treat an owner-set value as the owner's decision: if the key exists with a different value, log it and keep it
6. Make it idempotent: compute the new text, compare with the old, write only on change; a second install must be byte-identical
7. Do not record the file in installed_files.json: a manifest entry makes the next install drift-capture the owner's edits or prune the file as stale
8. Test through the real install path twice (stub only the auth signature) with a CRLF fixture, a pre-existing user file, a damaged-marker case and an owner-value case
9. Add a doctor check that reports (warns or notes, does not fail) when the expected region is missing

## Outputs

- Installer helper pair: pure text transform (old text in, new text or None out) plus a thin writer
- Regression tests for idempotency, byte preservation, CRLF, damage and owner value
- doctor note or warning for a missing region

## Notes

- Instances in governance-core: _configure_gitignore (runtime block, P-0129 F10), _ensure_boundary_anchor (settings.json projectRoot, F3), _install_pre_commit (whole-file hook owned only while it carries our marker line; foreign hook and core.hooksPath left alone, F9), _configure_gitattributes (merge=ours line)
- A whole file can be "owned" by a marker line instead of a block: refresh it only while the marker is present, so the owner takes it over by deleting one line
- Path.write_text on Windows translates newlines to CRLF and read_text folds CRLF to LF; both silently rewrite every line of a LF or CRLF file
- Recording a seeded file in the manifest is what deleted deva-vani's mixed clauses on the second install (P-0129 F2): same root cause, different file
- .gitignore additions do not untrack files already committed; report them (git rm --cached) instead of untracking automatically
