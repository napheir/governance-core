# -*- coding: utf-8 -*-
"""Proposal lifecycle helper library + CLI (P-0001 Phase 2).

Provides atomic operations for the /proposal skill v2:
  - `allocate-id`: filelock-protected next-ID allocator (scans all in-flight
    + archive paths, returns max+1 as P-NNNN)
  - `create`: writes v2 scaffold to shared_state/proposals/<agent>/
  - `transition`: atomic frontmatter + State Log append per state transition
  - `archive`: move terminal proposal from shared_state to _archive/<YYYY>/
  - `list`: tabular pending/in-flight/archive listing
  - `show`: display frontmatter + body preview
  - `path`: resolve P-NNNN to its current file path (in-flight or archive)

The skill markdown (.claude/commands/proposal.md) invokes this CLI per
subcommand; agent supplies decision context (e.g., user approval signal)
and never directly edits frontmatter — atomicity guaranteed by filelock +
os.replace().

Contracts:
  - contracts/proposal_frontmatter_schema.md v1.1.0 (id / agent / status /
    state-conditional fields)
  - config/proposals_config.json (paths, lock, agents enum)

CLI exit codes: 0 = success, 1 = validation / state error, 2 = lock timeout.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

import filelock

# Resolve repo root from this file's location (tools/proposal_lib.py).
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
from config import load_proposals_config  # noqa: E402


# ---------------------------------------------------------------------------
# Path / config resolution
# ---------------------------------------------------------------------------

def _config() -> dict:
    """Load proposal config (raises FileNotFoundError if missing)."""
    return load_proposals_config()


def _resolve(rel_path: str) -> Path:
    """Resolve a config-relative path to absolute Path (anchored at repo root)."""
    return (REPO_ROOT / rel_path).resolve()


def _in_flight_root() -> Path:
    return _resolve(_config()["shared_state_proposals_dir"])


def _archive_root() -> Path:
    return _resolve(_config()["archive_dir"])


def _snapshot_root() -> Path:
    return _resolve(_config()["snapshot_dir"])


def _lock_path() -> Path:
    return _resolve(_config()["lock_path"])


def _lock_timeout() -> int:
    return int(_config()["lock_timeout_sec"])


def _agents() -> list:
    return list(_config()["agents"])


def _id_ledger_path() -> Path:
    return _resolve(_config()["id_ledger_path"])


# ---------------------------------------------------------------------------
# Agent detection
# ---------------------------------------------------------------------------

_ROLE_MAP = {
    "master": "core",
    "main": "core",
    "feature/rules": "rules",
    "feature/trade": "trade",
    "feature/data": "data",
    "feature/research": "research",
}


def detect_agent() -> str:
    """Detect current agent from git branch name.

    Returns one of {core, rules, trade, data, research}. Falls back to 'core'
    if branch is unrecognized (e.g., detached HEAD on master).
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=REPO_ROOT,
        )
        branch = result.stdout.strip()
    except Exception:
        return "core"
    for prefix, role in _ROLE_MAP.items():
        if branch == prefix or branch.startswith(prefix):
            return role
    return "core"


# ---------------------------------------------------------------------------
# Frontmatter parsing / serialization
# ---------------------------------------------------------------------------

_FRONTMATTER_OPEN = re.compile(r"\A---\s*\n")
_ID_RE = re.compile(r"^P-(\d{4,})$")
_FILENAME_ID_RE = re.compile(r"^p-(\d{4,})-")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_proposal(path: Path) -> tuple[dict, str]:
    """Parse a proposal file into (frontmatter_dict, body_text).

    Raises ValueError on malformed frontmatter.
    """
    text = path.read_text(encoding="utf-8")
    if not _FRONTMATTER_OPEN.match(text):
        raise ValueError(f"{path}: no frontmatter (file must start with '---')")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"{path}: frontmatter not closed")
    fm_block = text[4:end]
    body = text[end + 5:]
    fm = {}
    current_list_key = None
    for line in fm_block.splitlines():
        stripped = line.rstrip()
        if not stripped:
            current_list_key = None
            continue
        if stripped.startswith("- ") and current_list_key:
            fm[current_list_key].append(stripped[2:].strip().strip("'\""))
            continue
        current_list_key = None
        if ":" not in stripped:
            continue
        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
        elif val == "":
            fm[key] = []
            current_list_key = key
        else:
            fm[key] = val
    return fm, body


def serialize_frontmatter(fm: dict) -> str:
    """Serialize frontmatter dict to YAML-like block (deterministic key order)."""
    field_order = [
        "id", "agent", "status", "created",
        "approved_at", "started_at",
        "implemented_in", "implemented_at",
        "rejected_at", "rejection_reason",
        "superseded_by", "supersedes", "related",
        "owner",
    ]
    lines = ["---"]
    for key in field_order:
        if key not in fm:
            continue
        val = fm[key]
        if isinstance(val, list):
            if not val:
                continue
            inline = ", ".join(val)
            lines.append(f"{key}: [{inline}]")
        else:
            lines.append(f"{key}: {val}")
    for key, val in fm.items():
        if key in field_order:
            continue
        if isinstance(val, list):
            inline = ", ".join(val)
            lines.append(f"{key}: [{inline}]")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_atomic(path: Path, content: str) -> None:
    """Write file atomically: write to tmp + os.replace()."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

VALID_STATUS = {
    "draft", "pending", "approved", "in-progress",
    "implemented", "superseded", "rejected",
}

TERMINAL_STATUS = {"implemented", "rejected", "superseded"}

ALLOWED_TRANSITIONS = {
    "draft": {"pending"},
    "pending": {"approved", "rejected"},
    "approved": {"in-progress", "implemented", "superseded"},
    "in-progress": {"implemented", "superseded"},
}


def _today() -> str:
    return _dt.date.today().isoformat()


# ---------------------------------------------------------------------------
# State Log append (body modification)
# ---------------------------------------------------------------------------

_STATE_LOG_HEADER = "## State Log"


def append_state_log(body: str, prev: str, new: str, note: str = "") -> str:
    """Append a transition line to the body's `## State Log` section.

    If the section doesn't exist, create it at the body end. Format:
      `- YYYY-MM-DD: prev → new [note]`
    """
    today = _today()
    note_suffix = f" ({note})" if note else ""
    entry = f"- {today}: {prev} → {new}{note_suffix}"
    if _STATE_LOG_HEADER in body:
        return body.rstrip() + "\n" + entry + "\n"
    sep = "\n\n" if not body.endswith("\n\n") else ""
    return body.rstrip() + sep + "\n\n" + _STATE_LOG_HEADER + "\n\n" + entry + "\n"


# ---------------------------------------------------------------------------
# Path discovery: given P-NNNN, find its current file (in-flight or archive)
# ---------------------------------------------------------------------------

def _scan_in_flight_paths() -> list[Path]:
    """All in-flight proposal files across all agent buckets."""
    root = _in_flight_root()
    if not root.exists():
        return []
    return sorted(root.glob("*/p-*.md"))


def _scan_archive_paths() -> list[Path]:
    """All archived proposal files across all years."""
    root = _archive_root()
    if not root.exists():
        return []
    return sorted(root.glob("*/p-*.md"))


def _scan_legacy_paths() -> list[Path]:
    """Pre-v1.1.0 proposals at agent-core/proposals/*.md (top level only).

    Files matching `p-NNNN-*` are NEW-scheme proposals living at legacy root
    (transition window); files without that prefix are pre-existing legacy.
    Both included for ID allocation max-scan.
    """
    legacy_root = REPO_ROOT / "proposals"
    if not legacy_root.exists():
        return []
    return sorted(p for p in legacy_root.glob("*.md") if p.is_file())


def find_by_id(proposal_id: str) -> Optional[Path]:
    """Resolve P-NNNN to current file path (in-flight | archive | legacy).

    Scan order: in-flight → archive → legacy. Returns None if not found.
    Raises ValueError if found in BOTH in-flight and archive (mutex violation).
    """
    if not _ID_RE.match(proposal_id):
        raise ValueError(f"Invalid id format: {proposal_id!r} (expected P-NNNN)")
    nnnn = proposal_id.split("-")[1]
    candidates = []
    for path in _scan_in_flight_paths():
        if path.name.startswith(f"p-{nnnn}-"):
            candidates.append(("in-flight", path))
    for path in _scan_archive_paths():
        if path.name.startswith(f"p-{nnnn}-"):
            candidates.append(("archive", path))
    for path in _scan_legacy_paths():
        if path.name.startswith(f"p-{nnnn}-"):
            candidates.append(("legacy", path))
    if not candidates:
        return None
    if len(candidates) > 1:
        regions = sorted({c[0] for c in candidates})
        if len(regions) > 1:
            raise ValueError(
                f"{proposal_id} exists in multiple regions {regions}: "
                f"{[str(p) for _, p in candidates]} — "
                "Art.5.1 mutex violation, manual cleanup required"
            )
    return candidates[0][1]


# ---------------------------------------------------------------------------
# ID allocator (filelock-protected, P-0001 Phase 1 lock_path)
# P-0057 Phase 1: A2 ledger SoT (shared_state/proposals/_id_ledger.json)
# ---------------------------------------------------------------------------

LEDGER_VERSION = "1.0.0"


def _scan_all_existing_ids() -> set[int]:
    """Collect numeric NNNN from all in-flight + archive + legacy filenames.

    Used for ledger bootstrap + drift reconciliation (guards against the
    case where ledger lags filesystem after manual cherry-pick).
    """
    ids = set()
    for paths in (_scan_in_flight_paths(), _scan_archive_paths(), _scan_legacy_paths()):
        for path in paths:
            m = _FILENAME_ID_RE.match(path.name)
            if m:
                ids.add(int(m.group(1)))
    return ids


def _bootstrap_ledger_entries() -> list[dict]:
    """Scan all existing proposal files and build initial ledger entries.

    Used both on first-run (ledger file missing) and by `migrate-ledger`
    CLI. Dedup by id (mutex violations across regions are flagged in audit
    but bootstrap picks the first-seen region for the entry).
    """
    entries_by_id: dict[str, dict] = {}
    region_order = [
        ("in-flight", _scan_in_flight_paths()),
        ("archive", _scan_archive_paths()),
        ("legacy", _scan_legacy_paths()),
    ]
    for region, paths in region_order:
        for path in paths:
            m = _FILENAME_ID_RE.match(path.name)
            if not m:
                continue
            nnnn = int(m.group(1))
            pid = f"P-{nnnn:04d}"
            if pid in entries_by_id:
                continue  # first-seen-wins (cross-region mutex flagged in audit)
            agent_field = "unknown"
            slug_field = path.stem[len(f"p-{m.group(1)}-"):]
            try:
                fm, _ = parse_proposal(path)
                agent_field = fm.get("agent", "unknown") if isinstance(fm, dict) else "unknown"
            except Exception:
                pass
            entries_by_id[pid] = {
                "id": pid,
                "agent": agent_field,
                "slug": slug_field,
                "bootstrap_region": region,
                "bootstrap_at": _today(),
            }
    return sorted(entries_by_id.values(), key=lambda e: int(e["id"].split("-")[1]))


def _read_ledger() -> dict:
    """Read ledger, or bootstrap from filesystem scan if missing.

    Returns dict with keys: version, next_id, entries (list).
    Bootstrap-on-miss makes deployment automatic: first allocate / create
    after deploy materializes the ledger.
    """
    p = _id_ledger_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    entries = _bootstrap_ledger_entries()
    if entries:
        max_nnnn = max(int(e["id"].split("-")[1]) for e in entries)
    else:
        max_nnnn = 0
    return {
        "version": LEDGER_VERSION,
        "next_id": max_nnnn + 1,
        "entries": entries,
    }


def _write_ledger(ledger: dict) -> None:
    """Atomic write of ledger file."""
    p = _id_ledger_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(ledger, indent=2, ensure_ascii=False) + "\n"
    write_atomic(p, content)


def _next_id_canonical(ledger: dict) -> int:
    """Compute canonical next ID: max(ledger.next_id, fs_scan_max + 1).

    The max-with-scan defense covers the case where someone manually
    cherry-picks an archived proposal into master (bumping scan ids past
    ledger next_id — exactly the P-0056 dogfood event that triggered
    P-0057). Without it the ledger could allocate a duplicate.
    """
    scan_ids = _scan_all_existing_ids()
    max_scan = max(scan_ids) if scan_ids else 0
    return max(int(ledger.get("next_id", 1)), max_scan + 1)


def allocate_next_id() -> str:
    """Filelock-protected: return next P-NNNN (read-only preview).

    Reads ledger SoT, reconciles against fs scan as anti-drift defense,
    but does NOT write back — that happens in `create_proposal` when the
    ID is actually consumed. Two concurrent CLI `allocate-id` calls may
    return the same ID; that's intentional (preview semantics).
    """
    lock = filelock.FileLock(str(_lock_path()), timeout=_lock_timeout())
    with lock:
        ledger = _read_ledger()
        nxt = _next_id_canonical(ledger)
        return f"P-{nxt:04d}"


# ---------------------------------------------------------------------------
# v2 scaffold
# ---------------------------------------------------------------------------

def _v2_scaffold(proposal_id: str, title: str, agent: str) -> str:
    """Generate v2 9-section body scaffold (P-0001 Phase 2 spec)."""
    today = _today()
    fm = {
        "id": proposal_id,
        "agent": agent,
        "status": "draft",
        "created": today,
        "owner": agent,
    }
    body = f"""# Proposal {proposal_id}: {title}

## Trigger

<User request and why proposal governance applies.>

## Scope

<What will be changed.>

## Non-Goals

<Explicitly out-of-scope items.>

## Guardrails

<Audit which guards apply: command-guard / scope-guard / sensitive-data-guard / edit-write-guard / boundary-guard.>

## Phases

### Phase 0: <Governance bootstrap, when applicable>

- Deliverables:
- Validation:
- Exit criteria:

### Phase 1: <Next phase>

- Deliverables:
- Validation:
- Exit criteria:

## Approval Criteria

<Concrete checks user can review before approval.>

## Validation Plan

<Commands, inspections, or manual checks.>

## Rollback / Recovery

<How to revert or disable the change per phase.>

## Risks

<Known risks, probability, impact, mitigation.>

## State Log

- {today}: draft created by {agent} agent ({proposal_id})
"""
    return serialize_frontmatter(fm) + "\n" + body


# ---------------------------------------------------------------------------
# create_proposal: allocate-id + scaffold write under filelock
# ---------------------------------------------------------------------------

def create_proposal(slug: str, title: str, agent: Optional[str] = None) -> Path:
    """Create new v2 proposal. Returns the absolute file path.

    Atomicity: lock held during ID allocation AND file write; another
    concurrent caller blocks. Slug must be filesystem-safe.
    """
    if not slug or not re.match(r"^[a-z0-9][a-z0-9_]*$", slug):
        raise ValueError(
            f"Invalid slug {slug!r}: must be lowercase alphanumeric/underscore, "
            "starting with a letter or digit"
        )
    agent = agent or detect_agent()
    if agent not in _agents():
        raise ValueError(f"Invalid agent {agent!r}; allowed: {_agents()}")

    lock = filelock.FileLock(str(_lock_path()), timeout=_lock_timeout())
    with lock:
        ledger = _read_ledger()
        nxt_num = _next_id_canonical(ledger)
        proposal_id = f"P-{nxt_num:04d}"
        filename = f"p-{nxt_num:04d}-{slug}.md"
        out_dir = _in_flight_root() / agent
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / filename
        if out_path.exists():
            raise FileExistsError(f"Collision: {out_path} already exists")
        content = _v2_scaffold(proposal_id, title, agent)
        write_atomic(out_path, content)
        # P-0057 Phase 1: append ledger entry + bump next_id atomically
        ledger.setdefault("version", LEDGER_VERSION)
        ledger.setdefault("entries", [])
        ledger["entries"].append({
            "id": proposal_id,
            "agent": agent,
            "slug": slug,
            "created": _today(),
        })
        ledger["next_id"] = nxt_num + 1
        _write_ledger(ledger)
    return out_path


# ---------------------------------------------------------------------------
# transition: atomic frontmatter + State Log update
# ---------------------------------------------------------------------------

def transition_proposal(
    proposal_id: str,
    new_status: str,
    *,
    note: str = "",
    rejection_reason: str = "",
    commit_hash: str = "",
    superseded_by: str = "",
) -> tuple[Path, str, str]:
    """Atomic state transition with State Log append.

    Returns (path, prev_status, new_status). Caller (skill) is responsible
    for checking user authorization signal for approve/reject.

    Filelock held during read-modify-write of the proposal file.
    """
    if new_status not in VALID_STATUS:
        raise ValueError(f"Invalid status {new_status!r}; allowed: {VALID_STATUS}")
    path = find_by_id(proposal_id)
    if path is None:
        raise FileNotFoundError(f"Proposal {proposal_id} not found")

    lock = filelock.FileLock(str(_lock_path()), timeout=_lock_timeout())
    with lock:
        # Re-read inside lock for atomicity
        fm, body = parse_proposal(path)
        prev = fm.get("status", "draft")

        # Validate transition (supersede can come from any state)
        if new_status == "superseded":
            pass
        elif prev not in ALLOWED_TRANSITIONS or new_status not in ALLOWED_TRANSITIONS[prev]:
            raise ValueError(
                f"Transition {prev} → {new_status} not allowed for {proposal_id}; "
                f"valid next states from {prev}: {ALLOWED_TRANSITIONS.get(prev, set())}"
            )

        today = _today()
        fm["status"] = new_status

        if new_status == "approved":
            fm["approved_at"] = today
        elif new_status == "in-progress":
            fm["started_at"] = today
        elif new_status == "implemented":
            if not commit_hash:
                commit_hash = _resolve_head_hash()
            _verify_commit_hash(commit_hash)
            fm["implemented_in"] = commit_hash
            fm["implemented_at"] = today
        elif new_status == "rejected":
            if not rejection_reason:
                raise ValueError("rejected requires --reason")
            fm["rejected_at"] = today
            fm["rejection_reason"] = rejection_reason
        elif new_status == "superseded":
            if not superseded_by:
                raise ValueError("superseded requires --superseded-by <path>")
            fm["superseded_by"] = superseded_by

        new_body = append_state_log(body, prev, new_status, note)
        # Normalize: strip leading whitespace from body to prevent
        # accumulating blank lines on repeated read-modify-write cycles.
        new_content = serialize_frontmatter(fm) + "\n" + new_body.lstrip("\n")
        write_atomic(path, new_content)

    _write_snapshot(proposal_id, new_status, path)
    return path, prev, new_status


def _resolve_head_hash() -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%h"],
        capture_output=True, text=True, timeout=5, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git log failed: {result.stderr}")
    return result.stdout.strip()


def _verify_commit_hash(commit_hash: str) -> None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", commit_hash + "^{commit}"],
        capture_output=True, text=True, timeout=5, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise ValueError(f"commit hash {commit_hash!r} not resolvable: {result.stderr.strip()}")


def _write_snapshot(proposal_id: str, status: str, src_path: Path) -> None:
    """Audit ledger: dump a copy to audit/proposal_snapshots/<id>/<status>.md.

    Append-only ledger (P-0001 Rollback risk mitigation: covers
    shared_state-not-in-git data loss). Skip for legacy paths (path is
    already in git).
    """
    if src_path.is_relative_to(REPO_ROOT / "proposals"):
        return  # legacy, already in git
    snap_dir = _snapshot_root() / proposal_id
    snap_dir.mkdir(parents=True, exist_ok=True)
    dst = snap_dir / f"{status}.md"
    dst.write_text(src_path.read_text(encoding="utf-8"), encoding="utf-8")


# ---------------------------------------------------------------------------
# Archive: move terminal in-flight to _archive/<YYYY>/
# ---------------------------------------------------------------------------

def archive_proposal(proposal_id: str, force_agent: bool = False) -> tuple[Path, Path]:
    """Move terminal proposal from in-flight to _archive/<YYYY>/.

    Returns (src_path, dst_path). Source must be terminal status and live
    in in-flight region (not legacy). Year derived from terminal-state date.

    P-0057 Phase 2: enforce owner check. The frontmatter `agent` field
    must equal the current branch's detected agent; otherwise raise
    PermissionError. `force_agent=True` (CLI: `--force-agent`) bypasses
    this check — escape hatch for core agent cleaning up orphan archives
    or correcting historical mis-assignments.
    """
    path = find_by_id(proposal_id)
    if path is None:
        raise FileNotFoundError(f"Proposal {proposal_id} not found")
    fm, _ = parse_proposal(path)
    status = fm.get("status")
    if status not in TERMINAL_STATUS:
        raise ValueError(f"Cannot archive {proposal_id}: status {status!r} not terminal")
    if not path.is_relative_to(_in_flight_root()):
        raise ValueError(f"Cannot archive {path}: not in shared_state in-flight region")

    # P-0057 Phase 2: owner enforcement
    owner = fm.get("agent")
    current = detect_agent()
    if not force_agent and owner != current:
        raise PermissionError(
            f"Owner mismatch on archive: {proposal_id} agent={owner!r} but current "
            f"branch detects agent={current!r}. Cross-owner archive blocked per "
            f"Art.5.1 (P-0057 Phase 2). If this is a legitimate core cleanup, "
            f"pass --force-agent."
        )

    date_field = {
        "implemented": "implemented_at",
        "rejected": "rejected_at",
        "superseded": "approved_at",  # superseded may lack a *_at; use approved_at as proxy
    }[status]
    date_str = fm.get(date_field, _today())
    year = date_str[:4] if _DATE_RE.match(date_str) else _today()[:4]
    dst_dir = _archive_root() / year
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / path.name
    if dst.exists():
        raise FileExistsError(f"Archive collision: {dst} already exists")

    lock = filelock.FileLock(str(_lock_path()), timeout=_lock_timeout())
    with lock:
        content = path.read_text(encoding="utf-8")
        write_atomic(dst, content)
        path.unlink()
    return path, dst


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_allocate_id(args):
    print(allocate_next_id())
    return 0


def _cmd_create(args):
    path = create_proposal(slug=args.slug, title=args.title, agent=args.agent)
    print(f"[OK] Created {path.relative_to(REPO_ROOT.parent)}")
    fm, _ = parse_proposal(path)
    print(f"     id={fm['id']} agent={fm['agent']} status={fm['status']}")
    return 0


def _cmd_transition(args):
    path, prev, new = transition_proposal(
        args.id,
        args.to,
        note=args.note or "",
        rejection_reason=args.reason or "",
        commit_hash=args.commit or "",
        superseded_by=args.superseded_by or "",
    )
    print(f"[OK] {args.id}: {prev} → {new}")
    print(f"     path: {path.relative_to(REPO_ROOT.parent)}")
    return 0


def _cmd_archive(args):
    src, dst = archive_proposal(args.id, force_agent=args.force_agent)
    print(f"[OK] Archived {args.id}")
    print(f"     from: {src.relative_to(REPO_ROOT.parent)}")
    print(f"     to:   {dst.relative_to(REPO_ROOT.parent)}")
    return 0


def _cmd_migrate_ledger(args):
    """Initialize / rebuild the ID ledger by scanning all proposal files.

    Idempotent: re-running rebuilds entries from filesystem. Useful after
    manual archive cherry-picks or when ledger is suspected corrupt.
    """
    lock = filelock.FileLock(str(_lock_path()), timeout=_lock_timeout())
    with lock:
        entries = _bootstrap_ledger_entries()
        max_nnnn = (
            max(int(e["id"].split("-")[1]) for e in entries) if entries else 0
        )
        ledger = {
            "version": LEDGER_VERSION,
            "next_id": max_nnnn + 1,
            "entries": entries,
        }
        if args.dry_run:
            print(f"[DRY-RUN] would write {_id_ledger_path().relative_to(REPO_ROOT.parent)}")
            print(f"          entries: {len(entries)}  next_id: P-{max_nnnn + 1:04d}")
            return 0
        _write_ledger(ledger)
        print(f"[OK] Ledger written: {_id_ledger_path().relative_to(REPO_ROOT.parent)}")
        print(f"     entries: {len(entries)}  next_id: P-{max_nnnn + 1:04d}")
    return 0


def _cmd_path(args):
    path = find_by_id(args.id)
    if path is None:
        print(f"[NOT FOUND] {args.id}", file=sys.stderr)
        return 1
    print(path)
    return 0


def _cmd_list(args):
    in_flight = _scan_in_flight_paths()
    archive = _scan_archive_paths() if args.include_terminal else []
    rows = []
    for path in in_flight:
        try:
            fm, _ = parse_proposal(path)
        except ValueError:
            continue
        rows.append((fm.get("id", "?"), fm.get("agent", "?"),
                     fm.get("status", "?"), "in-flight", path.name))
    for path in archive:
        try:
            fm, _ = parse_proposal(path)
        except ValueError:
            continue
        rows.append((fm.get("id", "?"), fm.get("agent", "?"),
                     fm.get("status", "?"), "archive", path.name))
    rows.sort()
    print(f"{'ID':<8} {'Agent':<10} {'Status':<14} {'Region':<10} File")
    print("-" * 70)
    for r in rows:
        print(f"{r[0]:<8} {r[1]:<10} {r[2]:<14} {r[3]:<10} {r[4]}")
    print(f"\n[Total: {len(rows)}]")
    return 0


def _cmd_show(args):
    path = find_by_id(args.id)
    if path is None:
        print(f"[NOT FOUND] {args.id}", file=sys.stderr)
        return 1
    fm, body = parse_proposal(path)
    print(f"=== {args.id} ===")
    print(f"Path: {path.relative_to(REPO_ROOT.parent)}")
    print(f"Frontmatter: {json.dumps(fm, indent=2, ensure_ascii=False)}")
    print(f"\nBody preview (first 30 lines):")
    for line in body.splitlines()[:30]:
        print(f"  {line}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("allocate-id", help="Print next P-NNNN id")
    p.set_defaults(func=_cmd_allocate_id)

    p = sub.add_parser("create", help="Create new v2 proposal scaffold")
    p.add_argument("--slug", required=True, help="filesystem-safe slug (lowercase / digits / underscore)")
    p.add_argument("--title", required=True, help="Proposal title (free text)")
    p.add_argument("--agent", default=None, help="Owner agent (default: auto-detect from branch)")
    p.set_defaults(func=_cmd_create)

    p = sub.add_parser("transition", help="Apply state transition with State Log append")
    p.add_argument("--id", required=True, help="P-NNNN")
    p.add_argument("--to", required=True, choices=sorted(VALID_STATUS))
    p.add_argument("--note", default="", help="Free-text note appended to State Log line")
    p.add_argument("--reason", default="", help="Rejection reason (required for --to rejected)")
    p.add_argument("--commit", default="", help="Commit hash (required for --to implemented; default HEAD)")
    p.add_argument("--superseded-by", default="", help="Replacement proposal path (required for --to superseded)")
    p.set_defaults(func=_cmd_transition)

    p = sub.add_parser("archive", help="Move terminal proposal to _archive/<YYYY>/")
    p.add_argument("--id", required=True)
    p.add_argument("--force-agent", action="store_true",
                   help="Bypass owner check (P-0057 Phase 2 escape hatch)")
    p.set_defaults(func=_cmd_archive)

    p = sub.add_parser("migrate-ledger",
                       help="Initialize / rebuild _id_ledger.json from filesystem scan")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be written without modifying ledger file")
    p.set_defaults(func=_cmd_migrate_ledger)

    p = sub.add_parser("path", help="Print absolute path for P-NNNN")
    p.add_argument("--id", required=True)
    p.set_defaults(func=_cmd_path)

    p = sub.add_parser("list", help="List proposals (default: in-flight only)")
    p.add_argument("--include-terminal", action="store_true",
                   help="Also include archive/")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("show", help="Show proposal frontmatter + body preview")
    p.add_argument("--id", required=True)
    p.set_defaults(func=_cmd_show)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except filelock.Timeout:
        print(f"[FAIL] filelock timeout ({_lock_timeout()}s) — another process holds the lock", file=sys.stderr)
        return 2
    except (ValueError, FileNotFoundError, FileExistsError, PermissionError, RuntimeError) as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
