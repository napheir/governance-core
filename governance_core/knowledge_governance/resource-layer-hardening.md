---
title: "Resource-layer hardening"
tags: [governance, security, defense-in-depth, hardening, os]
status: active
created: 2026-05-01
updated: 2026-06-24
owner: core
carrier_class: reference
related:
  - knowledge/governance/agent-least-privilege.md
---

# Resource-layer hardening (Phase D defense-in-depth)

Companion to all hook-layer defenses (proposal #3, harden-guard, and the
Phase A/B/C hardenings of `harden_indirect_attack_paths`). The hook layer
relies on string-level pattern matching at PreToolUse / PostToolUse;
this layer relies on the operating system + Git itself + DBMS authz
to refuse destructive operations even when the hook layer fails or is
bypassed.

This is **reference material**, not enforcement code. Each item lists
recommended action + threat model + cost. User picks based on personal
risk tolerance.

---

## 1. Why this layer exists

PreToolUse hooks scan command text. Defeated by:

- **Indirect via Python script**: LLM writes `cleanup.py` containing
  `shutil.rmtree(target)`, then runs `python cleanup.py`. The Bash
  command `python cleanup.py` has no destructive verb. Phase B of
  `harden_indirect_attack_paths.md` reduces this via content scan, but
  the warn-tier still allows pass-through for variable-arg forms.
- **PowerShell variable indirection**: `$cmd = "Re" + "move-Item"; & $cmd
  -Recurse -Force .git`. String-level regex cannot reliably catch this.
- **Compiled binaries**: LLM produces a Go/Rust binary that the user
  compiles + runs. Hook sees `./bin` only.
- **Network destruction**: `curl -X DELETE https://api/...`. Out of
  scope for any local hook.

For all of these, the durable line of defense is **at the resource**:
the OS, the Git repository, the DBMS, the file system. If the resource
itself refuses the destructive op, no LLM cleverness matters.

---

## 2. Recommended hardenings

### 2.1 Git repository immutable (Linux + macOS)

**Action**: mark `.git/objects/pack/` and key refs as read-only at the
filesystem level so even `rm -rf .git` from a privileged process fails.

```bash
# Linux: chattr immutable bit (requires root)
sudo chattr +i <install-root>/agent-core/.git/refs
sudo chattr +i <install-root>/agent-core/.git/objects/pack

# To allow a legitimate gc / pack-refs op, temporarily remove:
sudo chattr -i <install-root>/agent-core/.git/refs
git -C <install-root>/agent-core/ gc
sudo chattr +i <install-root>/agent-core/.git/refs
```

**Threat caught**: `rm -rf .git`, `git update-ref -d`, `find . -delete`
inside `.git/`, even via Python `os.unlink('.git/refs/heads/main')`.

**Cost**: medium. Needs sudo. Legitimate ops (gc, pack-refs, branch
delete) need temporary unset. Not Windows-portable as-is.

### 2.2 Git repository ACL (Windows)

**Action**: use Windows ACL to deny `Delete` on `.git/`:

```powershell
$acl = Get-Acl "~/workshop-claude/agent-core\.git"
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
  "$env:USERNAME", "DeleteSubdirectoriesAndFiles, Delete",
  "ContainerInherit,ObjectInherit", "None", "Deny"
)
$acl.AddAccessRule($rule)
Set-Acl "~/workshop-claude/agent-core\.git" $acl
```

**Threat caught**: same as 2.1.

**Cost**: medium. Same temporary-unset pattern for legit gc.

### 2.3 Credential file permissions

**Action**: tighten `~/.ssh/`, `~/.aws/credentials`, `~/.gcp/`,
`~/.gnupg/`, `~/.docker/config.json` to user-read-only and audit
unauthorized access via OS audit logs:

```bash
# Linux/macOS
chmod 700 ~/.ssh ~/.aws ~/.gnupg
chmod 600 ~/.ssh/id_* ~/.aws/credentials ~/.gnupg/*

# Linux audit (auditd):
sudo auditctl -w /home/<user>/.ssh -p wa -k claude_ssh_access
```

**Threat caught**: defense-in-depth even if `session-boundary-guard.py`
critical-paths list is bypassed (e.g., via privilege escalation or
hook-config tampering after override).

**Cost**: low. One-shot setup. Linux audit logs may need rotation
config.

### 2.4 RDBMS Agent runtime account

**Action**: never use a DB account with `DROP / TRUNCATE / DELETE
FROM (without WHERE)` privileges for the Agent's session credentials.
Issue a separate migration-role credential, scoped to a single session
or task, then revoked.

Already specified in `knowledge/governance/agent-least-privilege.md`
sec.2; this section just cross-references and notes the implementation
mechanism (per-engine):

```sql
-- PostgreSQL:
CREATE ROLE agent_runtime LOGIN PASSWORD '...';
GRANT CONNECT ON DATABASE proj TO agent_runtime;
GRANT USAGE ON SCHEMA public TO agent_runtime;
GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO agent_runtime;
-- explicitly NO DELETE, NO DROP, NO TRUNCATE.

-- MySQL/MariaDB:
GRANT SELECT, INSERT ON proj.* TO 'agent_runtime'@'localhost';
```

**Threat caught**: SQL DDL/DML destruction even when LLM-authored
script directly opens DB connection (bypasses shell layer).

**Cost**: low setup; ongoing op-discipline to use migration role only
when needed.

### 2.5 SQLite as filesystem-level concern

SQLite databases are **just files**. Filesystem layer's protections
apply directly:

- `agent_rules/<role>.allow.txt` controls which Agent role can write
  to which `*.db` / `*.sqlite` path
- `command-guard.py` regex blocks `> *.db` truncate-redirects
- `edit-write-guard.py` Layer 6 (Phase B) catches Python content like
  `os.unlink('important.db')`

If a SQLite database is **critical**:

- Schedule independent backup snapshot (cron + `cp` to a different
  directory; or btrfs / ZFS snapshot)
- Set OS-level read-only on the file outside business hours

### 2.6 Filesystem snapshots

**Action**: use OS-level snapshot mechanism so even total loss of
`<install-root>/` is recoverable.

| OS | Mechanism | Granularity |
|----|-----------|-------------|
| macOS | Time Machine (built-in) | hourly within 24h, daily for past month |
| Windows | File History / VSS / Restore Points | hourly to daily |
| Linux btrfs | `btrfs subvolume snapshot` (snapper, timeshift) | configurable, near-instant |
| Linux ZFS | `zfs snapshot` | configurable, near-instant |
| Linux ext4 | rsync to second disk + cron | configurable, slower |

**Threat caught**: total worktree destruction (any LLM-authored
attack that successfully wipes <install-root>/). Recovery via snapshot
restore.

**Cost**: low (snapshots are mostly free on btrfs/ZFS; modest for
rsync); requires the secondary storage if not snapshot-native.

### 2.7 SELinux / AppArmor profile (Linux)

**Action**: confine the Python interpreter that Claude Code spawns so
it cannot write to paths outside an explicit profile-allowlist.

Sketch (AppArmor):

```
profile claude-code-python /usr/bin/python3 {
  /home/<user>/AppData/Local/Programs/Python/Python311/<install-root>/** rw,
  /home/<user>/.claude/cache/** rw,
  /tmp/** rw,
  deny /home/<user>/.ssh/** w,
  deny /home/<user>/.aws/** w,
  deny /etc/** w,
}
```

**Threat caught**: any LLM-authored Python that opens file outside the
allowlist; bypasses all hook layers.

**Cost**: high setup (AppArmor / SELinux familiarity required), low
ongoing. Linux-only.

### 2.8 OS user with restricted sudo / admin

**Action**: run Claude Code under a user account WITHOUT sudo NOPASSWD
(Linux/macOS) or Administrator privileges (Windows). All destructive
ops requiring elevation will prompt for password / UAC, naturally
forcing user interaction.

**Threat caught**: privilege-escalation attempts via shell escape;
requests like `sudo rm -rf /` cannot complete without user input.

**Cost**: nil (just account hygiene).

---

## 3. Triage matrix: which hardenings to do first?

| Threat priority | Recommended hardenings |
|-----------------|------------------------|
| Critical (single-developer dev box, no recovery if wiped) | 2.6 snapshot + 2.8 unprivileged user |
| High (multi-system / shared) | + 2.1/2.2 git immutable, 2.3 cred chmod |
| Critical-path data (DB matters) | + 2.4 RDBMS least-priv, 2.5 SQLite chmod |
| Defense-in-depth maximalist | + 2.7 AppArmor/SELinux |

**Minimum recommended**: 2.6 (snapshot) + 2.8 (unprivileged user). Both
are zero-cost ongoing.

---

## 4. Trade-off vs hook-layer

This layer's strength: refuses dangerous ops at the OS / Git / DBMS,
not in shell-string pattern matching. Cannot be bypassed by clever
LLM scripting.

Weakness: must be configured per-machine by user; not portable across
clones. trade-agent's hook layer (proposal #3 + harden-guard +
harden_indirect_attack_paths) is portable via sync_infra; resource
layer is not.

**Recommended posture**: hook layer for portable, version-controlled
defense; resource layer for last-ditch unbypassable defense. Both are
necessary for serious work; neither alone is sufficient.

---

## 5. History

- 2026-05-01: introduced as Phase D of
  `proposals/harden_indirect_attack_paths.md`. Companion to
  `agent-least-privilege.md` (which focuses on credentials);
  this doc covers OS / FS / repo immutable / snapshots.
