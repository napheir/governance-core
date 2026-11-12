"""Who changed an agent's shared_state content, and telling that agent (P-0135).

contracts/shared_state_ownership.md §4-5. Three stores:

- the journal, `<shared_state>/_journal.jsonl`: append-only and hash-chained,
  one line per recorded write (a lib call, or an Edit/Write journaled by the
  own-write hooks, P-0136): `{ts, actor, op, path, sha_before, sha_after,
  via, prev[, notice]}`;
- notices, `<shared_state>/notices/<agent>/<id>.json`: what an agent and its
  owner must be told; acked ones move to `notices/<agent>/acked/`;
- the last-seen manifest, `<clone>/.governance/state_seen.json`: the shas this
  agent last saw in its own partitions (clone-local, gitignored).

`record_write` is the public API for gc libs and consumer libs. `scan` runs at
SessionStart (hooks/foreign-change-notice.py). It turns every change to the
agent's partitions that the agent did not make into a notice before the
manifest moves, so a change cannot drop out of sight. Single-agent projects
are a no-op throughout.
"""
from __future__ import annotations

import datetime
import hashlib
import importlib.util
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Any

import filelock

logger = logging.getLogger("governance_core.ownership")

JOURNAL_NAME = "_journal.jsonl"
JOURNAL_LOCK = "_journal.lock"
JOURNAL_ROTATE_BYTES = 5 * 1024 * 1024
NOTICES_DIR = "notices"
MANIFEST_REL = ".governance/state_seen.json"
PENDING_REL = ".governance/pending_writes"
PENDING_TTL_SECONDS = 24 * 3600
SHOWN_ACK_SESSIONS = 2
GATE_SEEN_REL = ".governance/notice_gate_seen.json"
GATE_SEEN_KEEP = 50
RECENT_DAYS = 7
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
VIAS = ("lib", "edit")
SCHEMA = 1


class OwnershipError(Exception):
    """An ownership operation was refused or could not run."""


# --- identity and paths -------------------------------------------------------

def _guard_common(project_root: Path):
    """Load the guards' _guard_common (installed copy first, then package)."""
    pkg = Path(__file__).resolve().parent
    for candidate in (project_root / ".claude" / "hooks" / "_guard_common.py",
                      pkg / "hooks" / "_guard_common.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location(
                "_gc_guard_common_ownership", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise OwnershipError("no _guard_common.py in .claude/hooks/ or the package")


def topology(project_root: Path) -> dict:
    """{"agents": [names], "core": name, "self": this clone's agent}."""
    gc = _guard_common(project_root)
    try:
        topo = gc.load_topology(str(project_root))
        me = gc.resolve_agent(str(project_root))
    except gc.TopologyError as exc:
        raise OwnershipError(f"agent identity unresolved: {exc}") from None
    return {"agents": [a["name"] for a in topo["agents"]],
            "core": topo["core"], "self": me}


def shared_root(project_root: Path) -> Path:
    """The project's shared_state root (config `shared_state_root`)."""
    return Path(_guard_common(project_root).shared_state_root(str(project_root)))


def shared_rel(project_root: Path, path: Path) -> str | None:
    """`path` relative to shared_state ('/'-separated), or None if outside."""
    gc = _guard_common(project_root)
    kind, rel = gc.shared_state_access(str(path), "", str(project_root))
    return None if kind == "outside" else rel


def owner_of(project_root: Path, rel: str, agents: list) -> str | None:
    """The agent whose partition holds shared_state path `rel`, if any."""
    gc = _guard_common(project_root)
    for name in agents:
        if any(gc._matches(rel, p) for p in gc.partition_patterns(name, str(project_root))):
            return name
    return None


def file_sha(path: Path) -> str | None:
    """sha256 of the file's bytes, or None when it does not exist."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


# --- journal --------------------------------------------------------------------

def _line_sha(line: str) -> str:
    return hashlib.sha256(line.rstrip("\n").encode("utf-8")).hexdigest()


def _rotations(root: Path) -> list:
    """Rotated journal files, oldest first."""
    def num(p: Path) -> int:
        return int(p.name.split(".")[1])
    return sorted((p for p in root.glob("_journal.*.jsonl")
                   if p.name.split(".")[1].isdigit()), key=num)


def _last_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    lines = [ln for ln in path.read_text(encoding="utf-8").split("\n") if ln.strip()]
    return lines[-1] if lines else None


def _append_journal(root: Path, record: dict) -> None:
    """Append `record` (prev filled in here) under the journal lock."""
    root.mkdir(parents=True, exist_ok=True)
    journal = root / JOURNAL_NAME
    with filelock.FileLock(str(root / JOURNAL_LOCK), timeout=10):
        if journal.is_file() and journal.stat().st_size >= JOURNAL_ROTATE_BYTES:
            nums = [int(p.name.split(".")[1]) for p in _rotations(root)]
            journal.rename(root / f"_journal.{max(nums, default=0) + 1}.jsonl")
        last = _last_line(journal)
        if last is None:
            rotated = _rotations(root)
            last = _last_line(rotated[-1]) if rotated else None
        record = dict(record, prev=_line_sha(last) if last is not None else None)
        with open(journal, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def journal_records(root: Path, rotated: bool = False) -> list:
    """Journal records, oldest first: the current file, or every file when
    `rotated` (the rotated files, then the current one)."""
    files = (_rotations(root) if rotated else []) + [root / JOURNAL_NAME]
    out = []
    for path in files:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"corrupt": line})
    return out


def _chain(records: list, rel: str, start: str | None, end: str | None) -> tuple:
    """(explained, consumed, follower) for a change of `rel` from `start` to `end`.

    Explained when a run of journal lines for `rel`, oldest first, leads from
    sha `start` to sha `end` (§4 "Explained changes"); a line that merely
    ends at `end` is not enough. `consumed` is that run. `follower` is the
    first line for `rel` after the run that did not continue it -- the write
    that came after a gap -- or None.
    """
    cur, consumed, follower = start, [], None
    for rec in records:
        if "path" not in rec or rec["path"] != rel:
            continue
        if rec["sha_before"] == cur:
            cur = rec["sha_after"]
            consumed.append(rec)
            follower = None
        elif follower is None:
            follower = rec
    return cur == end, consumed, follower


def _what(before: str | None, after: str | None) -> str:
    """'deleted', 'created' or 'changed' for a sha transition."""
    if after is None:
        return "deleted"
    return "created" if before is None else "changed"


def _gap_detail(what: str, follower: dict | None) -> str:
    """Notice detail for a change no journal run explains."""
    if follower is None:
        return f"{what} outside the governance libs; actor unknown"
    return (f"{what} outside the governance libs before {follower['op']} by "
            f"{follower['actor']}; actor unknown")


def verify_chain(root: Path) -> tuple:
    """(ok, detail): every line's `prev` is the sha of the line before it."""
    journal = root / JOURNAL_NAME
    if not journal.is_file():
        return True, ""
    rotated = _rotations(root)
    prev_line = _last_line(rotated[-1]) if rotated else None
    for n, line in enumerate(l for l in journal.read_text(encoding="utf-8").split("\n")
                             if l.strip()):
        try:
            rec = json.loads(line)
        except ValueError:
            return False, f"line {n + 1} is not JSON"
        want = _line_sha(prev_line) if prev_line is not None else None
        if "prev" not in rec or rec["prev"] != want:
            return False, f"line {n + 1} does not chain to the line before it"
        prev_line = line
    return True, ""


# --- notices --------------------------------------------------------------------

def write_notice(root: Path, agent: str, *, kind: str, severity: str, frm: str,
                 paths: list, commits: list | None = None, detail: str = "") -> str:
    """Write a notice for `agent`; return its id."""
    nid = f"{_now().replace('-', '').replace(':', '')}-{secrets.token_hex(3)}"
    _write_json_atomic(root / NOTICES_DIR / agent / f"{nid}.json", {
        "schema": SCHEMA, "id": nid, "ts": _now(), "from": frm, "kind": kind,
        "severity": severity, "paths": paths, "commits": commits or [],
        "detail": detail})
    return nid


def list_notices(root: Path, agent: str) -> list:
    """Un-acked notices of `agent`, oldest first."""
    folder = root / NOTICES_DIR / agent
    if not folder.is_dir():
        return []
    out = []
    for p in sorted(folder.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except ValueError:
            logger.warning("[ownership] unreadable notice %s", p)
    return out


def unacked_counts(root: Path, agents: list) -> dict:
    """{agent: number of un-acked notices} for agents that have any."""
    counts = {a: len(list_notices(root, a)) for a in agents}
    return {a: n for a, n in counts.items() if n}


def ack_notice(root: Path, agent: str, nid: str, acked_by: str) -> None:
    """Move notice `nid` of `agent` to acked/, stamping who and when."""
    src = root / NOTICES_DIR / agent / f"{nid}.json"
    if not src.is_file():
        raise OwnershipError(f"no un-acked notice {nid} for {agent}")
    data = json.loads(src.read_text(encoding="utf-8"))
    data.update(acked_by=acked_by, acked_at=_now())
    _write_json_atomic(root / NOTICES_DIR / agent / "acked" / src.name, data)
    src.unlink()


def mark_shown(root: Path, agent: str, nid: str, session_id: str) -> bool:
    """Record that session `session_id` displayed info notice `nid` of `agent`.

    The notice is acked (`acked_by: "shown-2"`) once SHOWN_ACK_SESSIONS
    distinct sessions have shown it; a resumed or compacted session keeps
    its id and never counts twice (§5). Returns True when it was acked.
    """
    src = root / NOTICES_DIR / agent / f"{nid}.json"
    if not src.is_file():
        return False
    data = json.loads(src.read_text(encoding="utf-8"))
    if data["severity"] != "info":
        raise OwnershipError(f"{nid} is an alert; only the owner acks alerts")
    shown = list(data["shown"]) if "shown" in data else []
    if session_id not in shown:
        shown.append(session_id)
    data["shown"] = shown
    _write_json_atomic(src, data)
    if len(shown) >= SHOWN_ACK_SESSIONS:
        ack_notice(root, agent, nid, f"shown-{SHOWN_ACK_SESSIONS}")
        return True
    return False


def list_acked(root: Path, agent: str, days: int = RECENT_DAYS) -> list:
    """Acked notices of `agent` whose acked_at is within `days`, newest first."""
    folder = root / NOTICES_DIR / agent / "acked"
    if not folder.is_dir():
        return []
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for p in folder.glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            logger.warning("[ownership] unreadable notice %s", p)
            continue
        if "acked_at" in data and data["acked_at"] >= since:
            out.append(data)
    return sorted(out, key=lambda n: n["acked_at"], reverse=True)


def alert_gate(project_root: Path, session_id: str) -> str | None:
    """UserPromptSubmit: the text to block this session's first prompt with.

    Returns None (let the prompt through) in a single-agent project, when
    this agent has no un-acked alert, or when this session was already
    gated. Otherwise records `session_id` in the clone-local
    GATE_SEEN_REL (last GATE_SEEN_KEEP ids) and returns the summary (§5).
    """
    project_root = Path(project_root)
    if not session_id:
        return None
    topo = topology(project_root)
    if len(topo["agents"]) < 2:
        return None
    me = topo["self"]
    alerts = [n for n in list_notices(shared_root(project_root), me)
              if n["severity"] == "alert"]
    if not alerts:
        return None
    seen_path = project_root / GATE_SEEN_REL
    seen = (json.loads(seen_path.read_text(encoding="utf-8"))["sessions"]
            if seen_path.is_file() else [])
    if session_id in seen:
        return None
    _write_json_atomic(seen_path, {"schema": SCHEMA,
                                   "sessions": (seen + [session_id])[-GATE_SEEN_KEEP:]})
    lines = [f"[Alerts pending] {me}: {len(alerts)} un-acked alert(s) about your "
             f"shared_state content:"]
    for n in alerts[:10]:
        paths = ", ".join(n["paths"][:3]) + (" ..." if len(n["paths"]) > 3 else "")
        lines.append(f"  [ALERT] {n['id']}: {n['kind']} from {n['from']} -- {paths}"
                     + (f" ({n['detail']})" if n["detail"] else ""))
    if len(alerts) > 10:
        lines.append(f"  ... and {len(alerts) - 10} more: python tools/notices.py list")
    lines.append("Your message was held once in this session so that you see these. "
                 "Resend it to continue. Once you have looked, tell the agent which "
                 "alerts to ack.")
    return "\n".join(lines)


# --- manifest and partitions ------------------------------------------------------

def load_manifest(project_root: Path) -> dict | None:
    """{rel: sha} this agent last saw, or None before the first scan."""
    path = project_root / MANIFEST_REL
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["files"])


def save_manifest(project_root: Path, files: dict) -> None:
    _write_json_atomic(project_root / MANIFEST_REL,
                       {"schema": SCHEMA, "files": dict(sorted(files.items()))})


def partition_files(project_root: Path, agent: str) -> dict:
    """{rel: sha} of every file in `agent`'s shared_state partitions."""
    gc = _guard_common(project_root)
    root = shared_root(project_root)
    out: dict = {}
    for pattern in gc.partition_patterns(agent, str(project_root)):
        if pattern.endswith("/**"):
            base = root / pattern[:-3]
            candidates = base.rglob("*") if base.is_dir() else []
        else:
            candidates = root.glob(pattern)
        for p in candidates:
            if p.is_file() and not p.name.endswith(".tmp"):
                rel = p.relative_to(root).as_posix()
                if gc._matches(rel, pattern):
                    out[rel] = file_sha(p)
    return out


# --- public API -------------------------------------------------------------------

def _severity(actor: str, via: str, core: str) -> str:
    """info only for a lib write by the core agent (§5); alert otherwise."""
    return "info" if actor == core and via == "lib" else "alert"


def record_write(project_root: Path, op: str, rel_path: str,
                 sha_before: str | None, sha_after: str | None,
                 via: str = "lib") -> None:
    """Record a write of shared_state path `rel_path` by this clone's agent.

    `via` is "lib" for a lib call and "edit" for an Edit/Write journaled by
    the own-write hooks. Appends a journal line.
    - If the actor owns the path: a change from the actor's last-seen sha to
      `sha_before` that no journal run explains becomes an alert first, so
      the write cannot absorb it; then the last-seen manifest moves.
    - If another agent owns it: that agent gets a foreign-write notice, info
      for a core lib write and alert otherwise.
    No-op in a single-agent project.
    """
    if via not in VIAS:
        raise OwnershipError(f"via must be one of {VIAS}, not {via!r}")
    project_root = Path(project_root)
    topo = topology(project_root)
    if len(topo["agents"]) < 2:
        return
    root = shared_root(project_root)
    actor = topo["self"]
    owner = owner_of(project_root, rel_path, topo["agents"])
    seen = load_manifest(project_root) if owner == actor else None
    if seen is not None:
        was = seen[rel_path] if rel_path in seen else None
        if was != sha_before:
            ok, _, _ = _chain(journal_records(root, rotated=True),
                              rel_path, was, sha_before)
            if not ok:  # the write that follows the gap is this one
                write_notice(root, actor, kind="foreign-write", severity="alert",
                             frm="unknown", paths=[rel_path],
                             detail=_gap_detail(_what(was, sha_before),
                                                {"op": op, "actor": actor}))
    record = {"ts": _now(), "actor": actor, "op": op, "path": rel_path,
              "sha_before": sha_before, "sha_after": sha_after, "via": via}
    if owner is not None and owner != actor:
        record["notice"] = write_notice(
            root, owner, kind="foreign-write",
            severity=_severity(actor, via, topo["core"]), frm=actor,
            paths=[rel_path], detail=f"{op} by {actor}")
    _append_journal(root, record)
    if seen is not None:
        if sha_after is not None:
            seen[rel_path] = sha_after
        elif rel_path in seen:
            del seen[rel_path]
        save_manifest(project_root, seen)


# --- Edit/Write journal (own-write hooks) -----------------------------------------

def _field(data: Any, key: str) -> Any:
    """data[key] when `data` is a dict holding `key`, else None."""
    return data[key] if isinstance(data, dict) and key in data else None


def edit_target(payload: dict) -> tuple | None:
    """(key, tool, absolute path) of a file-editing tool call, from hook input.

    The key is `tool_use_id`; without one, `<session_id>-<sha1 of path>`.
    None when the call is not a file edit or cannot be keyed.
    """
    tool = _field(payload, "tool_name")
    if tool not in EDIT_TOOLS:
        return None
    tool_input = _field(payload, "tool_input")
    raw = _field(tool_input, "file_path") or _field(tool_input, "notebook_path")
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    cwd = _field(payload, "cwd")
    if not path.is_absolute() and isinstance(cwd, str) and cwd:
        path = Path(cwd) / path
    key = _field(payload, "tool_use_id")
    if not isinstance(key, str) or not key:
        session = _field(payload, "session_id")
        if not isinstance(session, str) or not session:
            return None
        key = f"{session}-{hashlib.sha1(str(path).encode('utf-8')).hexdigest()[:16]}"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)
    return safe, tool, path


def _prune_pending(folder: Path) -> None:
    """Remove pending captures older than PENDING_TTL_SECONDS."""
    if not folder.is_dir():
        return
    cutoff = datetime.datetime.now().timestamp() - PENDING_TTL_SECONDS
    for p in folder.glob("*.json"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def capture_before(project_root: Path, payload: dict) -> None:
    """PreToolUse: store the sha of a partition file about to be edited.

    Writes `<clone>/.governance/pending_writes/<key>.json` = {path,
    sha_before, ts}. Only files in some agent's partition, only in a
    multi-agent project.
    """
    project_root = Path(project_root)
    target = edit_target(payload)
    if target is None:
        return
    key, _, path = target
    topo = topology(project_root)
    if len(topo["agents"]) < 2:
        return
    rel = shared_rel(project_root, path)
    if rel is None or owner_of(project_root, rel, topo["agents"]) is None:
        return
    folder = project_root / PENDING_REL
    _prune_pending(folder)
    _write_json_atomic(folder / f"{key}.json",
                       {"path": rel, "sha_before": file_sha(path), "ts": _now()})


def journal_edit(project_root: Path, payload: dict) -> None:
    """PostToolUse: journal the edit captured by capture_before().

    Reads and removes the pending capture, then records the write with
    `op` = "edit:<Tool>" and via "edit". Nothing is journaled without a
    capture or when the sha did not change.
    """
    project_root = Path(project_root)
    target = edit_target(payload)
    if target is None:
        return
    key, tool, path = target
    pending = project_root / PENDING_REL / f"{key}.json"
    if not pending.is_file():
        return
    data = json.loads(pending.read_text(encoding="utf-8"))
    pending.unlink()
    rel = shared_rel(project_root, path)
    sha_after = file_sha(path)
    if rel != data["path"] or sha_after == data["sha_before"]:
        return
    record_write(project_root, f"edit:{tool}", rel, data["sha_before"], sha_after,
                 via="edit")


def scan(project_root: Path) -> dict:
    """SessionStart: notice every foreign change to this agent's partitions.

    Returns {"agent", "core", "new": [notices created], "notices": [un-acked],
    "counts": {agent: n}, "chain_ok", "chain_detail", "first_run"}. The
    manifest is rewritten only after the notices are on disk.
    """
    project_root = Path(project_root)
    topo = topology(project_root)
    result = {"agent": topo["self"], "core": topo["core"], "new": [],
              "notices": [], "counts": {}, "chain_ok": True, "chain_detail": "",
              "first_run": False}
    if len(topo["agents"]) < 2:
        return result
    root = shared_root(project_root)
    me = topo["self"]
    current = partition_files(project_root, me)
    seen = load_manifest(project_root)
    if seen is None:
        result["first_run"] = True
    else:
        records = journal_records(root, rotated=True)
        for rel in sorted(set(current) | set(seen)):
            now_sha = current[rel] if rel in current else None
            was_sha = seen[rel] if rel in seen else None
            if now_sha == was_sha:
                continue
            what = _what(was_sha, now_sha)
            ok, consumed, follower = _chain(records, rel, was_sha, now_sha)
            if not ok:
                result["new"].append(write_notice(
                    root, me, kind="foreign-write", severity="alert", frm="unknown",
                    paths=[rel], detail=_gap_detail(what, follower)))
                continue
            for rec in consumed:  # own writes are silent; foreign ones told us
                if rec["actor"] == me or "notice" in rec:
                    continue
                via = rec["via"] if "via" in rec else "lib"
                result["new"].append(write_notice(
                    root, me, kind="foreign-write",
                    severity=_severity(rec["actor"], via, topo["core"]),
                    frm=rec["actor"], paths=[rel],
                    detail=f"{what} by {rec['actor']} ({rec['op']})"))
    save_manifest(project_root, current)
    result["chain_ok"], result["chain_detail"] = verify_chain(root)
    result["notices"] = list_notices(root, me)
    result["counts"] = unacked_counts(root, topo["agents"])
    return result
