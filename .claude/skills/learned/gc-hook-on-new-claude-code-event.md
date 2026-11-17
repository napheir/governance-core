---
name: gc-hook-on-new-claude-code-event
description: "When adding or moving a gc hook onto a Claude Code hook event that may be new or undocumented (e.g. PostToolUseFailure): verify the event in the installed binary, rely on unknown-event skipping for old clients, one manifest event per hook file, fail-open importer registration"
type: learned
layer: business
tags: [hooks, claude-code, manifest, runtime-import]
created: 2026-11-17
updated: 2026-11-17
---

# gc-hook-on-new-claude-code-event

When adding or moving a gc hook onto a Claude Code hook event that may be new or undocumented (e.g. PostToolUseFailure): verify the event in the installed binary, rely on unknown-event skipping for old clients, one manifest event per hook file, fail-open importer registration

## Preconditions

1. Change is in governance_core/hooks/ (package source)
2. The hook is best-effort (fail-open), not a guard

## Workflow

1. Verify the event exists in the installed client: grep -a -o -E '.{120}<EventName>.{200}' on the claude binary (path from 'command -v claude'); the event list and its input schema (tool_use_id, tool_input ...) are in there even when the CHANGELOG and hooks docs omit it
2. Check how older clients degrade: per the settings docs an unknown hook event name is a Settings Warning, only that entry is skipped and the rest of the file stays in effect; so never put a fail-closed guard on an event an older client may lack, only best-effort work
3. hooks_manifest.json maps ONE event per hook file: to serve a second event, add a small twin hook file that calls the same package function; do not change the manifest schema
4. If the hook imports governance_core: guard the import inside main()'s try, exit 0 on any error, and add the file to runtime_import_audit.FAIL_OPEN_GC_IMPORTERS; the audit is textual, so never hide an importer behind runpy
5. A matcher that lists Bash after a pipe character, typed inside a Bash command, trips command-guard's pipe-to-bash pattern; edit the manifest with the Edit tool or a patch script in artifacts/, and search with the Grep tool rather than shell grep
6. governance-core upgrade --project-root ., then read .claude/settings.local.json to confirm the new event group and matcher; full suite; doctor hooks / hooks_registered counts; wheel check that the new hooks/*.py is in it
7. Commit the tracked .claude/settings.local.json with the hook change (hub precedent) until it is untracked

## Outputs

- governance_core/hooks/<twin>.py
- governance_core/hooks/hooks_manifest.json
- governance_core/runtime_import_audit.py

## Notes

- P-0138 (2026-11-17): own-write-journal-failure.py on PostToolUseFailure, verified in Claude Code 2.1.286
- A docs-guide subagent first claimed the event existed, then retracted it; the binary grep settled it
