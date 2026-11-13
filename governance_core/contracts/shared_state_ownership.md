# Contract: Ownership of agent content in multi-agent projects

**Version**: 1.2.1
**Status**: active
**Owner**: core
**Consumers**:
- `tools/check_scope.py` (branch audit);
- `hooks/edit-write-guard.py`, `hooks/scope-guard.py`, `hooks/_guard_common.py` (partitions);
- `tools/proposal_lib.py` (owner checks, actor, journal);
- `governance_core/ownership.py` (journal, notices, last-seen manifest);
- `hooks/own-write-capture.py`, `hooks/own-write-journal.py` (Edit/Write journal);
- `hooks/foreign-change-notice.py` (SessionStart);
- `tools/notices.py` (list / ack / recent);
- `.claude/commands/{sync-repos,audit,publish-knowledge,proposal}.md`.

In a multi-agent project each agent works in its own clone and shares one `shared_state/` directory. This contract defines what each agent owns and how a change by anyone else is prevented, detected and reported (P-0135).

## 0. Threat model

- **Actors.** All agents are Claude Code sessions running as one OS user. A local hook cannot stop a determined process from writing a file.
- **Three guarantees.**
  - **Prevention** on every sanctioned and common write path (§2, §3).
  - **Detection**, from a vantage point the writer cannot alter, of anything that slipped past (§1, §4).
  - **Notification** of the affected agent and its owner (§5).
- **The property delivered:** no agent's content changes without that agent's owner being told.
- **Out of scope:** OS-level isolation (separate users, ACLs, a server-side store).
- **Single-agent projects** (`agents` length 1) are unaffected. Every check below is a no-op there.

## 1. Branch scope audit

`check_scope.py --audit-branch --agent <name> [--repo <clone>] [--ref <ref>] [--json]`
(`--agent <name>` with no other mode means the same thing).

**Where the audit runs.**
- **Auditing repo.** This is the clone the tool runs in. Run from core, it is the tamper-proof vantage point.
- **Audited ref.**
  - Default: `HEAD` of the auditing repo.
  - `--repo <clone>`: the tool first fetches that clone's current branch into the auditing repo as `refs/gc-audit/<agent>`, then audits it. The audited clone's own refs are never trusted.
  - `--ref <ref>`: audits any ref already present in the auditing repo, e.g. `origin/<branch>` after a fetch.

**Inputs.**
- **Core ref.** Config `upstream_branch`, else the first `core_branches` entry that resolves in the auditing repo.
- **Range.** `base = merge-base(core ref, audited ref)`. Every path whose content differs between `base` and the audited tip is examined (`git diff --no-renames --name-status`). This is the net change, merge resolutions included.
- **Rules.**
  - Allow rules: `git show <core ref>:agent_rules/<agent>.allow.txt`.
  - Deny rules: `git show <core ref>:agent_rules/shared.deny.txt`.
  - Never read from the audited branch or any working tree.
- **What passes.** A path passes when:
  1. it matches the allow rules and not the deny rules; or
  2. its tip blob is a version of that path committed in core history; or
  3. it is deleted at the tip and absent at the core ref's tip.

**Output.**
- Exit 0 means no violation; exit 1 means at least one; exit 2 means the audit could not run.
- `--json` prints one report:

```json
{"schema": 1, "agent": "platform", "ref": "refs/gc-audit/platform",
 "base": "<sha>", "core_ref": "origin/master",
 "violations": [{"path": "agent_rules/content.allow.txt", "status": "M",
                 "commits": ["<short sha> <subject>"], "owners": ["content"]}]}
```

- `owners` lists the agents whose allow rules (from the core ref) cover the path. It is empty for a path nobody owns.

**Callers.**
- `/sync-repos` runs the audit for each clone after the fetch and before the merge. A clone with violations is not synced; the others continue.
- `/audit` runs it for every config agent.
- `/publish-knowledge` runs it before any business→master promotion.
- `hooks/merge-audit.py` runs it after a merge, as an advisory in the agent's own clone.

## 2. shared_state partitions

- **Root.** The root is config `shared_state_root`.
- **Partitions of agent A:**
  - `proposals/<A>/**`;
  - each template in the optional config `shared_state_partitions` (a list of strings relative to the root) with `{agent}` replaced by A. Example: `["todos/{agent}/**"]`.
- **Lib-only files.** Ledger, lock, journal and notices: `proposals/_id_ledger.json*`, `_journal*` (the journal, its rotations and its lock), `notices/**`, plus every glob in the optional config `shared_state_lib_only` (relative to the root; e.g. a consumer lib's own ledger and lock: `["todos/_ledger.json*", "todos/*.lock"]`). They are written only by the libs, through Python, never with Edit, Write or a shell command.
- **Ownership is by path only.** A file belongs to an agent because it sits in that agent's partition, not because of a field inside it. A consumer collection that keeps every agent's items in one flat directory, with the owner in frontmatter, has no partition. Business Edit/Write and shell writes to it are denied (an "other shared_state path"), and it gets no change detection. A consumer that wants it protected moves it to a `{agent}` layout (e.g. `todos/{agent}/**`) and declares that in `shared_state_partitions`.
- **Consumer libs.** A consumer's own lib (e.g. a todo lib run as `python tools/todo_lib.py`) writes through Python, which the guards do not see. The rows below govern what the guards see. The lib keeps its own owner checks, and records its writes with the journal API (§4) so that they are attributed.

| Writer | Own partition | Another agent's partition | Lib-only file | Other shared_state path |
|---|---|---|---|---|
| business agent, Edit/Write | allow | deny | deny | deny |
| business agent, Bash write-shaped command | allow | deny | deny | deny |
| business agent, proposal_lib | allow | deny (owner check) | via lib only | n/a |
| core agent | allow | allow, attributed and noticed (§5) | via lib only | allow |

- **Edit/Write** means every Claude Code file-editing tool: `Edit`, `Write`, `MultiEdit` and `NotebookEdit` (target `file_path`, or `notebook_path`).
- **Bash write-shaped commands** are output redirects (`>`, `>>`), `tee`, `cp`, `mv`, `rm`, `rmdir`, `touch`, `mkdir`, `ln`, `sed -i`, and writes inside `python -c`. Any other way of writing a file is caught by detection (§4).

## 3. Proposal owner checks and actor

- **Proposal owner.** The owner of a proposal is its frontmatter `agent`.
- **Caller.** The caller is the agent of the clone running `proposal_lib` (config-derived identity).
- **Mutations that need the caller to be the owner or the core agent:** `create --agent X`, `transition`, `link`, `set_handoff_to`, `orchestrate` and `archive`. `--force-agent` is honoured for the core agent only.
- **Actor on State Log lines.** Every State Log line written by the lib ends in ` by <caller>`.

## 4. Journal and last-seen manifest

**Journal.** `<shared_state_root>/_journal.jsonl` is append-only, one JSON object per line:

```json
{"ts": "2026-11-06T09:00:00Z", "actor": "core", "op": "transition",
 "path": "proposals/content/p-0005-x.md", "sha_before": "<sha256|null>",
 "sha_after": "<sha256|null>", "via": "lib|edit",
 "prev": "<sha256 of the previous line|null>"}
```

- **Paths.** `path` is relative to the shared_state root, with `/` separators.
- **Hashes.**
  - `sha_*` is the sha256 of the file bytes, null when absent.
  - `sha_before` must be the sha of the file immediately before this write. Detection relies on it (see "Explained changes" below).
- **How the write was made.** `via` is `lib` for a lib call and `edit` for an Edit/Write journaled by the hooks below. A missing `via` (1.0.0 lines) means `lib`.
  - Hook-journaled lines have `op` = `edit:<ToolName>`, e.g. `edit:Edit`.
- **Hash chain.** `prev` chains the lines: an edit or truncation breaks the chain, and readers report a broken chain.
- **Rotation.** At 5 MB the file is renamed to `_journal.<n>.jsonl`. The first line of the new file carries the old file's last-line hash as `prev`. Readers that explain changes read the rotated files too.
- **Public API** for gc libs and consumer libs: `governance_core.ownership.record_write(project_root, op, rel_path, sha_before, sha_after, via="lib")`.
  - It appends a line, with the actor taken from the clone's config-derived identity.
  - If the actor owns the path, it first checks that the actor's last-seen sha leads to `sha_before`. If that change is not explained, it writes an alert (§5). Then it moves the actor's last-seen manifest to `sha_after`.
  - If another agent owns the path, it also writes that agent's foreign-write notice (§5).
  - `governance_core.ownership.file_sha(path)` returns the sha256, or None if the file is absent.

**Edit/Write journal.** In a multi-agent project, an Edit/Write (§2) of a shared_state file is journaled by two fail-open hooks:
- `hooks/own-write-capture.py` (PreToolUse) stores the file's current sha in `<clone>/.governance/pending_writes/<key>.json` as `{"path", "sha_before", "ts"}`.
  - `<key>` is the hook input's `tool_use_id`. Without one, it is `<session_id>-<sha1 of path>`.
  - The file is clone-local and gitignored. A pending file older than 24 hours is removed.
- `hooks/own-write-journal.py` (PostToolUse) reads and removes the pending file, then calls `record_write(op="edit:<Tool>", ..., via="edit")`.
  - It journals nothing when the pending file is missing or the sha did not change. A missing pending file therefore surfaces later as an unexplained change.
- Bash writes are not journaled. A shell write to an agent's own partition shows up as an unexplained change.

**Explained changes.** A change of path P from sha A to sha B is explained only when a run of journal lines for P, oldest first, leads from A to B:
- the first line has `sha_before` = A;
- each later line has `sha_before` = the previous line's `sha_after`;
- the last line has `sha_after` = B.

A journal line that merely ends at B does not explain the change.

**Last-seen manifest.** `<clone>/.governance/state_seen.json` is clone-local and gitignored:

```json
{"schema": 1, "files": {"proposals/content/p-0005-x.md": "<sha256>"}}
```

- It covers the agent's own partitions.
- It is updated when this agent's own write is recorded (lib or Edit/Write), after the gap check above.
- It is rewritten at the end of the agent's SessionStart, after foreign changes have been turned into notices (§5).

## 5. Notices and how they reach the owner

**Notice file.** A notice is `<shared_state_root>/notices/<agent>/<id>.json`:

```json
{"schema": 1, "id": "20261106T090000Z-1a2b3c", "ts": "...",
 "from": "core|<agent>|unknown", "kind": "scope-violation|foreign-write",
 "severity": "alert|info", "paths": ["..."], "commits": ["..."], "detail": "...",
 "shown": ["<session_id>", "..."]}
```

`shown` is present on info notices only (see Acknowledgement).

**Severity.**
- **info** is used for one case only: a lib write (`via: "lib"`) by the core agent into another agent's partition, attributed in the journal. Core is allowed to do this (§2), for example creating a coordination item for an agent.
- **alert** covers everything else:
  - scope violations;
  - changes that are not explained (§4), whose actor is unknown;
  - any write by a non-core agent into another agent's partition;
  - a core Edit/Write (`via: "edit"`) into another agent's partition, which bypasses the libs' checks.

  An alert repeats until the owner acks it.

**What writes a notice.**
- **scope-violation.** Core's branch audit (§1), when run with `--notify`, writes one per affected owner (each agent in `owners`) and one to the audited agent.
- **foreign-write**, three sources:
  - a recorded write (lib or Edit/Write) by agent B to agent A's partition, attributed to B;
  - at A's SessionStart, any file in A's partitions whose sha differs from A's last-seen manifest by a change that is not explained (§4). `from` is `unknown`. The detail names the first journaled write that followed the gap, if any;
  - an own write by A whose `sha_before` is not explained from A's last-seen sha (§4). The alert is written before the manifest moves, so the earlier change is not absorbed.

**How the owner sees it.**
- **At each SessionStart**, `hooks/foreign-change-notice.py`:
  1. persists foreign changes as notices, then rewrites the manifest;
  2. emits SessionStart hook JSON:
     - `systemMessage` lists this agent's un-acked notices plus a broken-chain warning, for the owner's UI;
     - `hookSpecificOutput.additionalContext` carries the same text and tells the agent to report it to the owner first;
  3. adds one line to every clone's output with the project-wide count of un-acked notices per agent.
- Alerts are not acked until the owner says so, so they keep reappearing at every SessionStart until the owner has seen them.
- **No hook changes a prompt or the session name.**
  - A blocked prompt is discarded, and the first prompt of a session can be a peer's cross-session message.
  - The session title is also the name peers use to address the session.

**Acknowledgement.**
- `python tools/notices.py ack <id>` moves the notice to `notices/<agent>/acked/` and adds `{acked_by, acked_at}`.
- An agent acks an alert only when its owner says so in that turn. Un-acked alerts repeat every session.
- An info notice records each distinct `session_id` that displayed it in `shown`. It is acked automatically (`acked_by: "shown-2"`) once two distinct sessions have shown it. Showing it again in the same session never counts twice.
- `python tools/notices.py list --recent [--days N]` lists acked notices whose `acked_at` falls within the last N days (default 7), newest first, for review after the fact.

## 6. Versioning

SemVer. Minor = a new optional field or a new notice kind. Major = a change to the partition rule, the journal chain or the report schema (needs a `proposals/` entry).

**Changes.**
- **1.2.1** (P-0136 field check): the session-title indicator is withdrawn.
  - In Claude Code the session title is also the cross-session address (the `ListAgents` name). Setting `[ALERT N] <agent>` renamed the session, and peers holding the old name could no longer reach it.
  - `notice-title.py` is gone, and `foreign-change-notice.py` never sets `sessionTitle`.
  - `.governance/notice_title.json` stays in the managed `.gitignore` block.
- **1.2.0** (P-0136): the session title shows un-acked alerts (`[ALERT N] <agent>`), through SessionStart and the new non-blocking `notice-title.py`. Nothing is held or dropped.
- **1.1.1** (P-0136 field check): the first-prompt alert gate (`hooks/notice-gate.py`) is withdrawn.
  - A blocked prompt is discarded, and the first prompt of a session can be a cross-session or other automated message, so that message was lost.
  - Claude Code also echoes the whole held prompt on screen.
  - A redesigned delivery is pending.
  - `.governance/notice_gate_seen.json` stays in the managed `.gitignore` block, so a leftover file stays ignored.
- **1.1.0** (P-0136):
  - Edit/Write is journaled (`via`, `op` = `edit:<Tool>`) and covers every file-editing tool.
  - Changes are explained only by a per-path run of journal lines, and own writes check that run before the manifest moves.
  - A core Edit/Write into another agent's partition is an alert.
  - Info notices are acked after two distinct sessions (`shown`, `shown-2`).
  - Alerts block the first prompt of a session once.
  - `notices.py list --recent` lists acked notices.
- **1.0.0** (P-0135): initial version.
