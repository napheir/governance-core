---
title: "Agent Runtime Least-Privilege Principle"
tags: [governance, security, least-privilege, defense-in-depth]
status: active
created: 2026-05-01
updated: 2026-06-01
owner: core
related:
  - agent_rules/shared.deny_commands.txt
  - agent_rules/shared.deny_commands_regex.txt
---

# Agent Runtime Least-Privilege Principle

> **Example content disclaimer**: The specific examples in this document (domain terminology, pipeline names, external API references, stock or asset identifiers, etc.) are drawn from the upstream project where governance-core was first developed. The patterns and principles are project-agnostic; downstream projects should substitute their own domain examples when applying the principles described here.


Forward-looking principle for any future RDBMS / external-API / privileged
runtime introduced into this project. Companion to the runtime-level
defense in `proposals/harden_destructive_command_guard.md`.

## 1. Principle

Any service or system that the Agent runtime has access to should be
configured so that the **default credentials** the Agent uses cannot
perform destructive operations. Destructive operations require a
**separate, human-issued, short-lived credential** — never the Agent's
session credentials.

This is **defense in depth**. PreToolUse regex layers (`command-guard.py`
Layer 1.5) block direct destructive commands at the shell level, but an
LLM-authored Python / SQL / API call can bypass shell-level guards
entirely. Authorization at the resource layer is the only durable
protection.

## 2. RDBMS specifics

When introducing any RDBMS (PostgreSQL, MySQL, SQLite, etc.), the Agent
runtime account **MUST NOT** by default have:

- `DROP TABLE` / `DROP DATABASE` / `DROP SCHEMA`
- `TRUNCATE TABLE`
- `DELETE FROM <table>` (without WHERE; or any DELETE on production
  tables — the line is "DELETE that loses irrecoverable rows")
- `ALTER TABLE ... DROP COLUMN`
- `GRANT` / `REVOKE` (role escalation)

Allowed by default:
- `SELECT` (read)
- `INSERT` (append-only)
- `UPDATE` with WHERE clause on non-history tables (not journals / audits)

When destructive operations are genuinely needed (data migration, schema
evolution), the human operator issues a separate **migration role**
credential, scoped to a single session or a single task, then revoked.

## 3. External API specifics

Agent should not have credentials for:

- API keys with `delete:*` / `admin:*` scopes
- Cloud provider IAM roles with destructive permissions (delete bucket,
  drop database, terminate instance)
- Production deploy / rollback credentials

If automation needs these, give it a separate identity that runs a fixed
playbook with human review before execution — not the Agent's
interactive session credentials.

## 4. External API credential isolation (Futu trade unlock as example)

This principle is **already partially enforced** in the project:

- `unlock_trade` substring is in `agent_rules/shared.deny_commands.txt`
  (blocked at the shell layer)
- Trade unlock + execution is gated by trade-only role scope in
  `agent_rules/trade.allow.txt`
- The actual external API/broker password is stored in user-managed config
  outside any Agent-scoped path

But the principle could be tightened further: the Agent could in
principle import `futu` and call unlock APIs without going through the
shell layer. A defense-in-depth fix is to move trade unlock to a
sub-process that the Agent invokes via a controlled IPC interface (e.g.,
write an "unlock requested" file, human watches and approves, daemon
unlocks) — not direct API calls from the LLM-authored code.

This is **not** scoped to be implemented today. It becomes actionable
when the Agent's trade automation moves from research / paper modes into
live execution.

## 5. SQLite caveat

SQLite databases are **just files**. RDBMS-level GRANT/REVOKE doesn't
apply — anyone with filesystem access can drop the file or rewrite it.
Therefore:

- SQLite files used by the project **must** be reachable via the
  filesystem layer's protections only:
  - `agent_rules/<role>.allow.txt` controls which Agent role can
    write to which path
  - `command-guard.py` blocks `rm` / redirect-truncate of `*.db` / `*.sqlite`
- Critical SQLite databases (if any) should be journaled / backed up
  externally on a schedule independent of the Agent's session

## 6. When this principle applies

Apply at design time of any new system:

- **Adding a new RDBMS** -> apply §2 before granting Agent credentials
- **Adding an external API integration** -> apply §3
- **Adding a new privileged daemon** -> apply §4-style indirection
- **Adopting a new state store** (KV cache, message queue, etc.) -> apply
  the analog of §2 (no destructive ops in default credentials)

This file should be referenced in the design proposal for any such
addition. If the proposal doesn't cite this principle, that's a review
finding.

## 7. History

- 2026-05-01: introduced as part of `harden_destructive_command_guard.md`
  (sec.2.6 forward-looking principle)
