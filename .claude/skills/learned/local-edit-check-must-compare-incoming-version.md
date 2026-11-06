---
name: local-edit-check-must-compare-incoming-version
description: "When code decides whether an installed file was locally edited by comparing it to a recorded baseline (manifest hash, cache, last-seen state) and the content can also arrive by a channel that does not update that baseline (git merge, sync, checkout): treat a file as edited only if it differs from BOTH the baseline and what this run is about to write"
type: learned
layer: candidate-common
tags: [installer, upgrade, drift, manifest, multi-clone, false-positive]
created: 2026-11-06
updated: 2026-11-06
---

# local-edit-check-must-compare-incoming-version

When code decides whether an installed file was locally edited by comparing it to a recorded baseline (manifest hash, cache, last-seen state) and the content can also arrive by a channel that does not update that baseline (git merge, sync, checkout): treat a file as edited only if it differs from BOTH the baseline and what this run is about to write

## Preconditions

1. The detector compares current content to a stored baseline
2. The baseline store does not travel with the content (untracked manifest, local cache)

## Workflow

1. List every channel that can change the file and mark which ones update the baseline (the installer does; git merge, /sync-repos and checkout do not)
2. Define a local edit as: differs from the baseline AND differs from what this run will write; a file already equal to the incoming version is not an edit
3. Compute the incoming version with the same function the writer uses, including rendering or placeholder substitution, never the raw source file
4. Hash both sides through one shared normalizer (e.g. EOL to LF) so the two comparisons cannot diverge
5. Map destination paths back to sources longest-prefix-first; nested destinations (a vendored package inside the hooks dir) otherwise resolve to a missing source and fall back to baseline-only
6. Do not suppress edits because the content matches upstream history in the clone that authors upstream: its own committed edits would then be overwritten silently; limit such checks to clones that only receive
7. Test through the real install path with a stale manifest (rewrite every baseline to an older version's hash) so every mapped category is exercised, then reverse-calibrate against the pre-fix code

## Outputs

- governance_core/installer.py (_capture_drift, _incoming_sha256, _pkg_source_path)
- governance_core/tools/test_installer_drift_merged_upstream.py

## Notes

- Origin: deva-vani 2026-11-06, 72 false candidate-common drift envelopes, fixed in 0.49.1
- The incoming-version check assumes the sender and receiver upgrade with the same package version; a receiver on a newer package still sees false drift
- Tests built on fake paths with no package source never exercise the source mapping; the real-install test exposed the _gc_auth gap at once
