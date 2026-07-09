---
title: P0-P4 Testing Pyramid & Audit Responsibilities
status: active
created: 2026-04-28
updated: 2026-04-28
owner: core
carrier_class: reference
tags: [governance, testing, audit, p0-p4]
briefing: pinned
---

# P0-P4 Testing Pyramid

Originally constitution Article 2.2. Migrated here on 2026-04-28 per
`proposals/slim_constitution_via_registry_and_router.md` Phase 2 — kept
in the constitution: only the red line "core agent 负责整体测试体系和
安全保障" + a pointer to this file.

---

## Five layers

| Layer | Name | Scope | Location |
|-------|------|-------|----------|
| **P0** | Contract tests | Verify cross-agent data format consistency, contract adherence | `tests/contracts/` |
| **P1** | Integration tests | Verify config completeness, scope rule correctness | `tests/integration/` |
| **P2** | Contract versioning | Manage contract evolution, compat checks, SemVer | `tests/contracts/test_contract_versions.py` |
| **P3** | E2E smoke tests | Quick pipeline connectivity (small dataset) | `tests/e2e/` |
| **P4** | Daily regression | Full system stability (frozen dataset) | `tests/daily/` + `tests/daily/MANUAL.md` |

## Daily regression manual

Core agent owns and maintains `tests/daily/MANUAL.md`:
- Test architecture, every test case explained
- Baseline management
- Report reading guide
- Troubleshooting
- Maintenance procedures

Update cadence: review every quarter, update immediately after major changes.

## Audit responsibilities (core agent)

1. **Scope compliance audit** — `tools/check_scope.py`; review changes to
   `agent_rules/*.allow.txt`; monitor cross-scope proposals
2. **Contract evolution audit** — review `contracts/` for backward compat;
   verify SemVer; flag breaking changes for documentation
3. **Config security audit** — scan `config/` for credential leaks; verify no
   hardcoding (Art.4); audit config-change blast radius
4. **Code quality audit** — run P0-P4; review test coverage; monitor failure
   trends as drift indicator
5. **Git discipline audit** — Conventional Commits adherence; branch policy;
   `.gitignore` for sensitive-file leakage

Audit reports go to `audit/`. Major violations block master merges. Monthly
summary digest expected.

## Test failure response (P4)

When P4 daily regression fails:

1. **Analyze immediately** — read report, locate failed stage and case
2. **Assess impact** — code regression / baseline drift / environment glitch?
3. **Notify**:
   - S3/S5 fail → rules-agent
   - S6/S9 fail → trade-agent
   - Data issue → data-agent
4. **Block release** — if master fails, halt prod deploy
5. **Track** — append to `audit/test_failures.log`

---

## See also

- `tests/daily/MANUAL.md` — operational manual
- `audit/` — audit log location
- `contracts/` — what P0/P2 verify
