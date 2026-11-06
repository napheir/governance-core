"""Who changed an agent's shared_state content, and telling that agent (P-0135).

contracts/shared_state_ownership.md §4-5. Three stores:

- the journal, `<shared_state>/_journal.jsonl`: append-only and hash-chained,
  one line per lib write: `{ts, actor, op, path, sha_before, sha_after,
  prev[, notice]}`;
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


def journal_records(root: Path) -> list:
    """Records of the current journal file (oldest first)."""
    journal = root / JOURNAL_NAME
    if not journal.is_file():
        return []
    out = []
    for line in journal.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"corrupt": line})
    return out


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

def record_write(project_root: Path, op: str, rel_path: str,
                 sha_before: str | None, sha_after: str | None) -> None:
    """Record a lib write of shared_state path `rel_path` by this clone's agent.

    Appends a journal line. If the actor owns the path, its last-seen
    manifest moves too (its own write is not news). If another agent owns
    it, that agent gets a foreign-write notice: info when the actor is the
    core agent, alert otherwise. No-op in a single-agent project.
    """
    project_root = Path(project_root)
    topo = topology(project_root)
    if len(topo["agents"]) < 2:
        return
    root = shared_root(project_root)
    actor = topo["self"]
    owner = owner_of(project_root, rel_path, topo["agents"])
    record = {"ts": _now(), "actor": actor, "op": op, "path": rel_path,
              "sha_before": sha_before, "sha_after": sha_after}
    if owner is not None and owner != actor:
        record["notice"] = write_notice(
            root, owner, kind="foreign-write",
            severity="info" if actor == topo["core"] else "alert", frm=actor,
            paths=[rel_path], detail=f"{op} by {actor}")
    _append_journal(root, record)
    if owner == actor:
        seen = load_manifest(project_root)
        if seen is not None:
            if sha_after is not None:
                seen[rel_path] = sha_after
            elif rel_path in seen:
                del seen[rel_path]
            save_manifest(project_root, seen)


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
        by_after: dict = {}
        for rec in journal_records(root):
            if "path" in rec:
                by_after[(rec["path"], rec["sha_after"])] = rec
        for rel in sorted(set(current) | set(seen)):
            now_sha = current[rel] if rel in current else None
            was_sha = seen[rel] if rel in seen else None
            if now_sha == was_sha:
                continue
            rec = by_after[(rel, now_sha)] if (rel, now_sha) in by_after else None
            if rec is not None and rec["actor"] == me:
                continue  # our own write; the manifest just lagged
            if rec is not None and "notice" in rec:
                continue  # record_write already told us
            frm = rec["actor"] if rec is not None else "unknown"
            what = "deleted" if now_sha is None else ("created" if was_sha is None else "changed")
            detail = (f"{what} by {frm} ({rec['op']})" if rec is not None
                      else f"{what} outside the governance libs; actor unknown")
            nid = write_notice(root, me, kind="foreign-write",
                               severity="info" if frm == topo["core"] else "alert",
                               frm=frm, paths=[rel], detail=detail)
            result["new"].append(nid)
    save_manifest(project_root, current)
    result["chain_ok"], result["chain_detail"] = verify_chain(root)
    result["notices"] = list_notices(root, me)
    result["counts"] = unacked_counts(root, topo["agents"])
    return result
