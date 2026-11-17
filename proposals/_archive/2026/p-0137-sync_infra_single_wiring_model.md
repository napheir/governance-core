---
id: P-0137
agent: core
status: implemented
created: 2026-11-12
approved_at: 2026-11-12
started_at: 2026-11-12
implemented_in: 2793803
implemented_at: 2026-11-17
owner: core
---

# Proposal P-0137: One wiring model: the installer distributes, sync_infra only checks

## Trigger

On 2026-11-10, deva-vani's core reported a bug in `tools/sync_infra.py`: it resolves every business clone to a directory that does not exist. In their layout, `sync_infra --execute` has always skipped every clone and still reported success ("Total pending actions: 0"). `/wrap-up` step 5 reads that as "nothing to sync".

Just fixing the path would be harmful. Once sync_infra finds the clones, it rewires six hooks in each clone to absolute paths into core. That fights the installer's clone-local wiring (P-0067), a conflict recorded but never resolved since P-0130.

The owner asked for a proposal that decides on one wiring model and fixes the path together with it. They called it "非常重要" (very important) on 2026-11-12 and agreed to draft it after P-0136, which is now released in 0.51.1.

## Current State (read, not assumed)

- **Clone paths.**
  - `governance_core/tools/sync_infra.py:41-63` builds `install_root / clone_dir` (`:51`, `:57`).
  - Every other tool resolves clones next to the core clone:
    - `governance_core/tools/audit_hooks.py:47` and `governance_core/tools/check_agent_roles.py:41` use `root.parent / clone_dir`;
    - `governance_core/tools/audit_sub_constitutions.py:55-85` does the same (P-0129 F7 family);
    - the guards derive the project directory from the clone's location (`governance_core/hooks/_guard_common.py:170-200`).
- **Measured on this machine (2026-11-12).**
  - Both multi-agent consumers use the nested `<root>/<project>/<clone>` layout, with `install_root = C:\Users\naphe\workshop-claude`:
    - `deva-vani`: agent-core, agent-platform, agent-experience, agent-content;
    - `auto-tax`: agent-core, agent-taxfiling.
  - So for both, sync_infra resolves `workshop-claude\agent-<x>`, which does not exist, and every clone hits `[SKIP] Directory not found` (`sync_infra.py:877-879`). The run still exits 0.
  - trade is not on this machine. Its layout is unverified.
- **What one sync_infra run does per clone** (`sync_infra.py:861-958`), and who already covers each step:
  1. **Copies `ALWAYS_COPY_FILES`** (`:88-219`; `.governance/sync_files.json` or a fallback): generator source, guards, contracts, two tests, one knowledge doc.
     - Covered elsewhere: gc-managed files come from `governance-core upgrade` per clone; tracked project files come from the `/sync-repos` merge.
  2. **Copies themed skills, commands and agents** from `SKILL_DIRS` (`:242-247`, `_discover_themed_copies` `:367`).
     - Covered elsewhere: the `/sync-repos` merge for tracked files and upgrade for gc-shipped ones.
     - `theme` itself is enforced at injection and audit time: `governance_core/discovery/registry.py`, `governance_core/hooks/session-context.py`, `governance_core/tools/audit_knowledge.py`.
  3. **Registers `CENTRAL_HOOKS`** (`:260-286`, `:901-916`): six hooks as absolute paths into core.
     - Conflicts with the installer's `${CLAUDE_PROJECT_DIR}` wiring.
     - `governance_core/installer.py:1102-1132` `_merge_hooks_block` treats a group whose hooks all point at manifest hook files as governance-owned, so upgrade drops and regenerates it. Each tool undoes the other.
  4. **Ensures `.claude/skills/learned`** (`:323-325`). Created on first use anyway.
  5. **Points guard references back at the clone** (`_fix_guard_references` `:653`). Installer wiring is always clone-local.
  6. **Removes stale central references** (`_cleanup_stale_central_refs` `:586`). Upgrade's regeneration covers groups made only of manifest hooks. Mixed groups are not covered.
  7. **Removes duplicate registrations** (`_cleanup_duplicates` `:701`). The installer regenerates its groups.
  8. **Narrows wide allow entries** (`_tighten_settings_local_allow` `:772`, list `:293-316`). Only sync_infra does this.
     - Measured: no wide entry (`Bash(rm:*)`, `Bash(del:*)`, `Bash(powershell:*)`, `Bash(pwsh:*)`) exists in any of the 6 consumer clones or on the hub. Every allow list is empty, and the user-global mode is `bypassPermissions`.
     - Destructive commands are stopped by `hooks/command-guard.py` regardless.
- **Central references today.** Zero absolute `agent-core/.claude/hooks` references in the 6 consumer clones' `settings.local.json`.
- **Who tells agents to run sync_infra.**
  - `governance_core/commands/wrap-up.md` step 5 (and 5b);
  - `governance_core/commands/sync-infra.md`;
  - `governance_core/commands/iterate-constitution.md:94-98, 117, 151, 173`;
  - `governance_core/commands/update-skill.md:17-102`;
  - mentions in `governance_core/commands/curate-candidate.md:65`, `learn.md:197`, `publish-knowledge.md:21`;
  - 7 shipped skills and 3 shipped knowledge docs (see Scope).

## Scope

- `governance_core/tools/sync_infra.py`: rewritten as a read-only check, keeping its name.
- New `governance_core/tools/test_sync_infra_check.py`. The existing sync_infra tests, `test_sync_infra_remove_local_copy.py` and the sync_infra use in `test_skill_injection_bounded.py`, are retired or adapted.
- Docs that tell agents to run `sync_infra --execute`, or describe it as distributing:
  - commands `wrap-up.md`, `sync-infra.md`, `iterate-constitution.md`, `update-skill.md`, `curate-candidate.md`, `learn.md`, `publish-knowledge.md`;
  - clause `art_15_skill_consultation_discipline.md`;
  - skills `cross-clone-base-promotion.md`, `proposal-vs-plan-mode-vs-commit.md`, `session-start-git-hygiene.md`, `settings-json-merge-semantics.md`, `skill-injection-tiers.md`, `skill-router-registration.md`, `slash-command-hot-reload.md`;
  - knowledge `proposal-classify-fast-path.md`, `resource-layer-hardening.md`, `skill-scenario-clusters.md`.
- `docs/core-manual.md`: the sync section.

## Design & Contract

### Interfaces, I/O & Realization

**The one wiring model (realized by `governance-core install/upgrade`, per clone).**
- Every clone wires every gc hook clone-locally (`${CLAUDE_PROJECT_DIR}/.claude/hooks/...`) from `hooks/hooks_manifest.json`.
- Files reach clones two ways: gc-managed files through `pip install -U` plus `governance-core upgrade --project-root <clone>` in each clone, and tracked project files through the `/sync-repos` merge.
- Nothing writes absolute paths into another clone.

**`python tools/sync_infra.py [--project-root <core clone>] [--agent X] [--json]`** becomes a read-only check, realized by the CLI. It runs from the core clone by default.
- **INPUT:** `.governance/config.json` (`agents[].name`, `clone_dir`, `core_agent_name`); each clone's `.claude/settings.local.json` (`hooks`, `permissions.allow`); `.governance/sync_files.json` `always_copy_files` when present.
- **Clone resolution:** `<core clone's parent>/<clone_dir>`, the same as audit_hooks and check_agent_roles.
- **Checks per business clone:**

  | check | result | printed fix |
  |---|---|---|
  | configured clone directory missing | FAIL | name the expected path; fix config `clone_dir` or clone it |
  | a hook command points outside this clone (e.g. at core's `.claude/hooks/`) | FAIL | `governance-core upgrade --project-root <clone>`; for a mixed group, remove the named entry |
  | a gc manifest hook is not registered clone-locally | FAIL | `governance-core upgrade --project-root <clone>` |
  | a wide allow entry from the §2.5 list is present | WARN | the narrow replacements, for the owner to apply |
  | a tracked `always_copy_files` path differs from core's copy | WARN | `/sync-repos` (merge) |

- **OUTPUT:** one `[OK]`/`[WARN]`/`[FAIL]` line per finding, grouped by clone; `--json` gives `{"clones": {name: {"path", "findings": [{"check", "level", "detail", "fix"}]}}}`.
- **Exit codes:** 0 = no FAIL, 1 = at least one FAIL, 2 = the check could not run (no config, unreadable settings).
- **`--execute`:** prints `[FAIL] sync_infra no longer copies or rewires; run /sync-repos and governance-core upgrade per clone` and exits 2. That way a stale `/wrap-up` copy cannot silently pass.
- **Single-agent project:** prints `[N/A] single-agent topology` and exits 0.

**`/wrap-up` step 5 (realized by the agent following the command).**
- Multi-agent: run the check, and fix every FAIL before the checklist can say "Infra: OK". WARNs are reported.
- Step 5b's trigger for `/sync-repos` stays as it is.

### Field Dictionary

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|
| config `agents[].clone_dir` | str | clone directory name next to the core clone | owner / installer | sync_infra check | existing field; N/A for contracts/ (config schema in `installer.py` `required_keys`, unchanged) |
| config `install_root` | str | no longer read by sync_infra | owner / installer | (none in sync_infra) | unchanged meaning elsewhere; N/A: no contract change |
| `.governance/sync_files.json` `always_copy_files` | list[str] | paths whose core copy should match each clone's | owner | the drift WARN only | optional, read-only now; N/A for contracts/ (project config, P-0059) |
| check finding `{check, level, detail, fix}` | object | one result | sync_infra | agent, `/wrap-up`, CI | `level` is `OK`, `WARN` or `FAIL`; `check` is `clone-missing`, `foreign-hook-ref`, `hook-unregistered`, `wide-allow` or `copy-drift`. N/A for contracts/: a tool report, documented in `commands/sync-infra.md` |
| exit code | int | overall result | sync_infra | `/wrap-up`, CI | 0 / 1 / 2 as above |

### Flow

```
config.json + each clone's settings.local.json (+ sync_files.json)
  -> sync_infra check (read-only, from the core clone)
  -> findings per clone -> stdout / --json -> exit 0|1|2
  -> /wrap-up step 5: FAIL -> fix as printed (upgrade, config, merge) -> re-run
distribution itself: pip -U -> governance-core upgrade per clone (gc files, hook wiring)
                     /sync-repos merge (tracked project files)
```

## Non-Goals

- No automatic rewrite of a consumer's `permissions.allow`. The wide-entry finding is a WARN with the exact replacements; the owner applies them. command-guard stops destructive commands regardless.
- No change to `governance-core doctor`. It could later reuse the foreign-hook-ref check per clone.
- No migration of `sync_files.json` (left in place, read only for the drift WARN).
- No change to `/sync-repos` itself, beyond docs that now point to it.

## Open Questions

1. **The allow-list tightening.** Report only (leaning), or keep an explicit `--tighten-allow` that rewrites the four wide entries? Report only, because the file is consumer-owned, nothing currently matches, and command-guard is the real control.
2. **`--execute`.** Leaning: refuse it with exit 2 and the new route. The alternative, quietly running the check, keeps old instructions "working" but hides that nothing is copied any more.
3. **Name.** Leaning: keep `sync_infra.py` and `/sync-infra`, so existing references and muscle memory still land somewhere that explains the change. The alternative is renaming to `check_infra.py`.
4. **trade.** Its layout is unverified. If it is flat, sync_infra has been active there and may have left central references. Leaning: after the release, ask trade's core to run the check before anything else and fix each FAIL as printed.

## Alternatives & Rationale

- **A. The installer is the only wiring model; sync_infra becomes a check (chosen).**
  - One source of truth for hook wiring, already used by every gc install.
  - Distribution is already covered by upgrade and the `/sync-repos` merge.
  - The check keeps the useful part of sync_infra: noticing a clone that is missing, mis-wired or drifting. It also fails loudly instead of skipping.
- **B. Keep sync_infra distributing, fix its paths, and make it wire clone-locally.** That means two tools writing the same files and settings. Its copies also bypass the installer's manifest, so upgrade later flags them as drift. Rejected.
- **C. Fix the path only.** That activates the central-wiring conflict in every nested-layout consumer. Rejected.
- **D. Delete sync_infra.** This loses the check, and stale `/wrap-up` copies would then hit "file not found" instead of a clear message. Rejected, in favour of reviving its intent as a check (see the retire-dead-code lesson: weigh a v2 before deleting).

## Guardrails

- **constitutional-review:** no `.get(k, default)` in rewritten code (the current file has several; the rewrite removes them); ASCII output.
- **Read-only:** the check never writes to any clone. Writes stay with upgrade and `/sync-repos`, which have their own guards.
- **scope-guard / edit-write-guard:** unchanged. The check only reads sibling clones, which is allowed. Writes outside the hub stay blocked by session-boundary-guard.

## Phases

### Phase 1: sync_infra becomes a check

- Deliverables:
  - `sync_infra.py` rewritten: clone resolution from the layout, the five checks, `--json`, exit codes, `--execute` refused.
  - `test_sync_infra_check.py`, with nested and flat layout fixtures.
  - Existing sync_infra tests retired or adapted; each disposition is listed in the commit.
- Validation:
  - Calibrate against 0.51.1: the nested-layout `clone-missing` silence and the exit 0 on all-SKIP are reproduced as failures there.
  - Full suite, command-guard script, doctor.
  - A live read-only run against deva-vani and auto-tax from the hub, with `--project-root` set to each consumer's core clone. Expected result: no FAIL.
- Exit criteria: committed; /wrap-up.

### Phase 2: Docs sweep

- Deliverables: every file in Scope says "run the check; distribution is upgrade plus `/sync-repos`". A grep gate lists any remaining `sync_infra.py --execute` or "sync_infra pushes / copies / routes" wording.
- Validation: `audit_knowledge` and the knowledge audits pass; the grep gate is empty.
- Exit criteria: committed; /wrap-up.

### Phase 3: Release and consumer check

- Deliverables:
  - With owner confirmation: release.
  - Ask deva-vani, auto-tax and trade (via their cores) to run the check after upgrading, and to report FAIL and WARN lines.
- Validation: each consumer reports exit 0, or each FAIL is fixed as printed.
- Exit criteria: reports received; complete and archive.

## Approval Criteria

> Each item pairs a plain-language acceptance with ONE discriminating check token
> (`cmd: <exit 0 = pass>` / `agent-rubric: <ref>` / `human-verify: <sentence>`; see
> contracts/proposal_gate_schema.md). An item with no check token is prose, not an
> acceptance signal.

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A) — human-verify: each row cites a file or says N/A with a reason
- [ ] Every user-facing capability / mutation has a named realizer — human-verify: the check, upgrade and /sync-repos each named as the realizer of their part
- [ ] All Open Questions are resolved or explicitly deferred — human-verify: the owner has ruled on OQ1-OQ4
- [ ] The check finds the clones in nested and flat layouts, fails on a missing clone and on a foreign hook reference, and refuses --execute — cmd: python -m pytest tools/test_sync_infra_check.py -q
- [ ] No regressions — cmd: python -m pytest tools/ maintainer/ -q
- [ ] No doc still tells an agent that sync_infra copies or rewires — agent-rubric: Phase 2 grep gate output is empty and each remaining mention describes the check
- [ ] Consumers report a clean check after upgrading — human-verify: deva-vani, auto-tax and trade each report exit 0 or list the FAILs they fixed

## Validation Plan

- Unit tests with nested and flat fixtures, calibrated against 0.51.1.
- A live read-only run against the two local consumers.
- The Phase 2 grep gate.
- Consumer reports in Phase 3.

## Rollback / Recovery

- Revert `sync_infra.py` to 0.51.1. Nothing is migrated, and the check writes nothing, so there is no data to restore.
- Docs revert with the same commit range.

## Risks

- **A consumer depended on sync_infra copying a project-specific file that is not tracked in git.** The `/sync-repos` merge would not carry it. Mitigation: the copy-drift WARN names such paths. Trade is asked to run the check first.
- **Mixed hook groups** (central and project hooks together) survive upgrade. Mitigation: the foreign-hook-ref FAIL names the exact entry to remove.
- **Stale `/wrap-up` copies** loaded early in a long session still say `--execute`. Mitigation: `--execute` exits 2 with the new route, so it cannot pass silently.

## As-built notes

**Phase 1 (2026-11-12)**
- **The rewrite.**
  - `sync_infra.py` was rewritten as a read-only check, going from 1061 lines to about 270. No `.get(k, default)` is left.
  - There is one extra FAIL check, `settings-missing`, for a missing or unreadable `settings.local.json`. It is reported per clone instead of aborting the whole run with exit 2.
  - Exit 2 is kept for a run that cannot happen at all: no config, an unknown `--agent`, or `--execute`.
- **Copy drift.**
  - It compares text with line endings normalised, so a CRLF-only difference is not drift.
  - Only paths that exist in core are compared.
- **Calibration** (`artifacts/p0137/calibrate_old_sync_infra.py`).
  - The 0.51.3 tool on a nested fixture with `install_root` = the project's parent skipped both clones, printed "Total pending actions: 0" and exited 0.
  - On the same fixture, the new check found both clones: "2 clone(s), 0 FAIL".
- **Live, read-only, from the hub.**
  - `--project-root ~/workshop-claude/deva-vani/agent-core` gave platform, experience and content all OK: 0 FAIL, 0 WARN.
  - `--project-root ~/workshop-claude/auto-tax/agent-core` gave taxfiling OK: 0 FAIL, 0 WARN.
- **Tests.** `test_sync_infra_remove_local_copy.py` was retired, because `_remove_local_copy` is gone. `test_sync_infra_check.py` has 10 tests. Full suite 549, command-guard 42/42, doctor OK.
- **For Phase 2.**
  - The guards' FATAL banners (`edit-write-guard.py:65`, `scope-guard.py:53`, `data-source-guard.py:64`) still say "python tools/sync_infra.py --execute".
  - `session-context.py:351` reads a `restart_required.json` that only the old tool wrote.
  - `regen_constitution.py:6` and `_guard_common.py:23` mention sync_infra distribution.
- **Version** 0.52.0, because `--execute` is refused, which can break a consumer script.

**Phase 2 (2026-11-12)**
- **Files rewritten.**
  - commands: wrap-up Step 5 now runs the check; 5b's trigger 1 and 2b's reason are reworded; the checklist line reads "Infra 已检查"; sync-infra is rewritten as the check; iterate-constitution's Step 5 table; update-skill's Step 3, the Step 1 grep and the checklist; curate-candidate; learn; publish-knowledge.
  - clause: `art_15` (`theme` is enforced by SessionStart injection and audit_knowledge).
  - skills: `cross-clone-base-promotion` and `slash-command-hot-reload` are rewritten for the one wiring model; `proposal-vs-plan-mode-vs-commit`, `session-start-git-hygiene`, `settings-json-merge-semantics`, `skill-injection-tiers` and `skill-router-registration` are reworded.
  - knowledge: `skill-scenario-clusters` (`theme` no longer moves files; the routing column is dropped), `resource-layer-hardening`, `proposal-classify-fast-path`.
  - code text:
    - the guards' FATAL banners in `edit-write-guard`, `scope-guard` and `data-source-guard` now say `governance-core upgrade --project-root <this clone>`;
    - `edit-write-guard`'s self-protection banner;
    - the `_guard_common`, `regen_constitution`, `registry`, `audit_knowledge`, `build_skill_index` and `test_skill_injection_bounded` docstrings;
    - `session-context`'s restart-marker docstring and message. Nothing writes that marker now; a leftover marker is still shown once.
  - docs: `architecture.md`; `core-manual.md`, with a new §16 "One wiring model".
- **Grep gate.** No remaining text tells an agent that sync_infra copies, routes or rewires. Every remaining mention describes the check, history (pre-0.52), or a path category (`proposal-classify-paths.json`).
- **Validation.** Full suite 549, command-guard 42/42, doctor OK, audit_knowledge healthy, `regen_constitution --check` in sync.

**Phase 3 (released 2026-11-13 as 0.52.0)**
- **deva-vani (reported 2026-11-16 by its core):** all four clones on 0.52.0.
  - Order: pip install, core upgrade (203 files overwritten, 34 real changes, `notice-title.py` and `test_sync_infra_remove_local_copy.py` pruned, no drift), master commit pushed, then in each business clone upgrade, blob check against origin/master, merge master, dry-run (no drift).
  - **Before the clone merges:** 0 FAIL, 15 WARN, all copy-drift, 5 per clone (`edit-write-guard.py`, `scope-guard.py`, `data-source-guard.py`, `_guard_common.py`, `knowledge/governance/resource-layer-hardening.md`). These were exactly the files the Phase 2 sweep changed, and the printed fix ("/sync-repos (merge), then governance-core upgrade") was right. This is the check's first true positive in the field.
  - **After the merges:** 3 clones, 0 FAIL, 0 WARN ("wired clone-locally, no drift"). The clones were found from config `clone_dir`; `install_root` was unchanged.
  - doctor in every clone: hooks=24, hooks_registered=23 (same as the hub). Their tools suite: 656 passed, 5 skipped.
- **auto-tax, trade:** not upgraded yet. auto-tax's read-only run from the hub in Phase 1 was clean.
- **Closed early by the owner (2026-11-17: "可以结案").** The exit criterion asked for reports from all three consumers. The owner closed it on deva-vani's report.
  - The remaining two are covered by `/wrap-up` Step 5: from 0.52.0 it runs the check, and every FAIL must be fixed before the checklist says "Infra 已检查". Their first wrap-up after upgrading is the check.
  - The request to run it and report rides on P-0132's upgrade request to auto-tax and trade.
- **Reconcile.** 0e1a3f8 (Phase 1) and 2793803 (Phase 2) together cover every scope file. The files touched outside scope are the guard banners and docstrings listed under "For Phase 2", plus STATE and the version bump. No substantive deviation.

## State Log

- 2026-11-12: draft created by core agent (P-0137)
- 2026-11-12: draft → pending (submit for review) by core
- 2026-11-12: pending → approved (owner: 批准 (decision-card defaults: OQ1 allow list report-only; OQ2 --execute refused with exit 2; OQ3 keep the sync_infra name; OQ4 trade runs the check first after release)) by core
- 2026-11-12: approved → in-progress (start Phase 1 (sync_infra becomes a check)) by core
- 2026-11-17: in-progress → implemented (owner: 可以结案 (closed on deva-vani's report; auto-tax and trade covered by /wrap-up Step 5 and the P-0132 upgrade request)) by core
