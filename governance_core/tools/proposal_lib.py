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
  - .governance/config.json — proposal paths / lock / agents enum are derived
    from it by governance_core.config.load_proposals_config (P-0066 Phase 1;
    replaced the legacy project-root config/proposals_config.json).

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

# Proposal config is derived from <REPO_ROOT>/.governance/config.json by the
# governance_core package (P-0066 Phase 1). The package is always pip-installed
# (the `governance-core` console script lives in it), so this import resolves
# from both the package source tree and any installed project's tools/ copy.
from governance_core.config import load_proposals_config


# ---------------------------------------------------------------------------
# Path / config resolution
# ---------------------------------------------------------------------------

def _config() -> dict:
    """Load proposal config (raises FileNotFoundError if config.json missing)."""
    return load_proposals_config(REPO_ROOT)


def _resolve(path_str: str) -> Path:
    """Normalize a proposal-config path string to an absolute Path.

    load_proposals_config() already returns absolute paths; this just resolves
    them (collapses any `..`/symlink components).
    """
    return Path(path_str).resolve()


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

## Current State (read, not assumed)

<Cite the files / line ranges / measured numbers you READ at the point of change -- not assumptions. At least one concrete file reference is required (e.g. `path/to/file.py:120`). This is a research floor enforced on approve; substance is the approver's call.>

## Scope

<What will be changed.>

## Design & Contract

> Proportionate. Trivial change: one line "implementation self-evident; no interface
> or data-flow change." Otherwise fill all three sub-parts; use "N/A — <reason>" for
> any that genuinely doesn't apply — never leave a placeholder.

### Interfaces, I/O & Realization
<Each new/changed boundary (fn / CLI / file / endpoint): its signature, the INPUT it
 consumes (record/file/params + which fields) and the OUTPUT it produces (record/file/
 return + which fields). For every user-facing capability and every mutation, NAME the
 component that actually performs it end-to-end (server / daemon / CLI / agent /
 static-file). A capability with no named backing mechanism is a design error — build
 it (name it) or declare it deferred in Non-Goals. No ambiguous middle.>

### Field Dictionary
<Every field that flows across a boundary. If persisted or cross-agent, NAME the
 governing contracts/ file (existing or "new: contracts/X") — do not invent a parallel
 vocabulary that drifts from contracts/.>

| field | type | meaning | producer | consumer | constraints / allowed values |
|-------|------|---------|----------|----------|------------------------------|

### Flow
<producer → transform → consumer → sink. Text arrows / ASCII / mermaid.>

## Non-Goals

<Explicitly out-of-scope items.>

## Open Questions

> Known-undecided design points to resolve (or explicitly defer) BEFORE approval.
> Lightweight — NOT gated; the approver decides each. Write "None" rather than leaving
> the placeholder.

- <question — plus the default/leaning if it stays unresolved, so silence resolves
  predictably instead of being decided ad-hoc at implementation time>

## Alternatives & Rationale

<Proportionate: a single obvious approach states "single obvious approach + why"; a design choice weighs >=2 options with the trade-off and records why the chosen one won.>

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

> Concrete checks to tick before approval — derive from the spec above, don't restate
> goals. For a complex proposal include, as applicable:

- [ ] Every Field Dictionary entry names its governing `contracts/` file (or is N/A)
- [ ] Every user-facing capability / mutation has a named realizer (nothing implied-but-unbuilt)
- [ ] All Open Questions are resolved or explicitly deferred
- [ ] <proposal-specific checks>

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
# P-0108: Plan-mode rigor — section helpers, Current State adequacy gate,
# as-built reconcile. These are FORM-only machine checks; whether research is
# *adequate* in substance is the human approver's judgment (form-vs-substance
# split). See knowledge/governance/proposal-drafting-checklist.md.
# ---------------------------------------------------------------------------

_CURRENT_STATE_HEADING = "## Current State"

# A concrete file/line reference: a filename with a known extension, or a
# `path:line` token. Shared by the adequacy gate and (loosely) reconcile.
_FILE_REF_RE = re.compile(
    r"[\w./\\-]+\.(?:py|md|json|jsonl|toml|txt|ya?ml|cfg|ini|sh|ps1|js|ts|tsx|html|css)\b"
    r"|[\w./\\-]+:\d+"
)


def _extract_section(body: str, heading_prefix: str) -> str:
    """Return the text under a `## Heading` line, up to the next `## ` or EOF.

    Matches by prefix so `## Current State (read, not assumed)` is found via
    `## Current State`. Returns '' if the heading is absent. H3 (`### `) lines
    inside the section are preserved (only H2 boundaries close it).
    """
    out: list[str] = []
    capturing = False
    for line in body.splitlines():
        if line.startswith("## "):
            if capturing:
                break
            if line.strip().startswith(heading_prefix):
                capturing = True
            continue
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def current_state_adequacy(body: str) -> tuple[bool, str]:
    """Form-only adequacy check for the `## Current State` section.

    Returns (is_adequate, reason). Verifies the section is PRESENT, is not just
    the scaffold placeholder, and cites >=1 concrete file/line reference. This
    is the SHARED predicate used by both the `transition --to approved` BLOCK
    and the audit WARN (Check 13) so the two can never disagree. It checks FORM
    only — adequacy of substance is the human approver's call (P-0108).
    """
    if _CURRENT_STATE_HEADING not in body:
        return False, "missing '## Current State (read, not assumed)' section"
    content = _extract_section(body, _CURRENT_STATE_HEADING)
    filled = re.sub(r"<[^>]*>", "", content).strip()  # drop scaffold placeholders
    if not filled:
        return False, "Current State is empty or still the scaffold placeholder"
    if not _FILE_REF_RE.search(filled):
        return False, ("Current State cites no concrete file/line reference "
                       "(e.g. path/to/file.py:120)")
    return True, "ok"


def _extract_scope_file_tokens(body: str) -> list[str]:
    """Loosely extract file-like tokens from the `## Scope` section.

    Loose by design (advisory reconcile): any token that looks like a path with
    a known extension. Backticks stripped; line-number suffix dropped;
    de-duplicated; order-stable.
    """
    section = _extract_section(body, "## Scope")
    seen: list[str] = []
    for m in _FILE_REF_RE.finditer(section):
        tok = m.group(0).strip("`")
        if ":" in tok:  # keep the path, drop the :line form for scope tokens
            tok = tok.split(":", 1)[0]
        if tok and tok not in seen:
            seen.append(tok)
    return seen


def _loose_file_match(token: str, path: str) -> bool:
    """True if a loose scope token plausibly refers to a changed file path."""
    t = token.replace("\\", "/").lower().strip("`")
    p = path.replace("\\", "/").lower()
    if not t:
        return False
    if t in p:
        return True
    return Path(t).name == Path(p).name


def _commit_changed_files(commit_ish: str) -> list[str]:
    """Repo-relative paths changed by a commit (or an `A..B` range).

    text=True alone would decode child stdout as GBK on a Windows CN hub
    (subprocess-text-decodes-gbk); pin encoding='utf-8'.
    """
    if ".." in commit_ish:
        cmd = ["git", "diff", "--name-only", commit_ish]
    else:
        cmd = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_ish]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8",
        timeout=10, cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise ValueError(
            f"git changed-files failed for {commit_ish!r}: {result.stderr.strip()}"
        )
    return [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]


def reconcile(proposal_id: str, commit_ish: str) -> dict:
    """As-built coverage: `## Scope` file-tokens vs a commit's changed files.

    Advisory (loose token match by design). Returns a dict with two coverage
    lists: `in_scope_not_touched` (declared in Scope but unchanged) and
    `touched_not_in_scope` (changed but not declared). Agent reviews; not
    machine-enforced.
    """
    path = find_by_id(proposal_id)
    if path is None:
        raise FileNotFoundError(f"Proposal {proposal_id} not found")
    _, body = parse_proposal(path)
    scope_tokens = _extract_scope_file_tokens(body)
    changed = _commit_changed_files(commit_ish)
    in_scope_not_touched = [
        tok for tok in scope_tokens
        if not any(_loose_file_match(tok, c) for c in changed)
    ]
    touched_not_in_scope = [
        c for c in changed
        if not any(_loose_file_match(tok, c) for tok in scope_tokens)
    ]
    return {
        "scope_tokens": scope_tokens,
        "changed": changed,
        "in_scope_not_touched": in_scope_not_touched,
        "touched_not_in_scope": touched_not_in_scope,
    }


# ---------------------------------------------------------------------------
# P-0124: Design & Contract gate — a proportionate, complexity-gated design
# spec section. Like the P-0108 Current State gate these are FORM-only machine
# checks (placeholder-replaced / sub-parts present); whether the design is
# *correct* is the human approver's call. `design_contract_adequacy` is the
# shared predicate behind both the `transition --to approved` BLOCK (complex
# proposals only) and audit Check 14 (WARN), so the two can never disagree.
# ---------------------------------------------------------------------------

_DESIGN_CONTRACT_HEADING = "## Design & Contract"
_DESIGN_CONTRACT_SUBHEADINGS = (
    "### Interfaces, I/O & Realization",
    "### Field Dictionary",
    "### Flow",
)

# A `### Phase` heading whose title is a `<...>` scaffold placeholder doesn't
# count toward complexity; a bare `### Phase N` with no title doesn't either.
_PHASE_HEADING_RE = re.compile(r"^###\s+Phase\b(.*)$")

# Scaffold Field-Dictionary header cells (P-0124). A table row whose non-empty
# cells are all drawn from this set is the empty scaffold skeleton, not data;
# a markdown separator row (cells of only -/:) is likewise skeleton.
_FIELD_DICT_HEADER_CELLS = {
    "field", "type", "meaning", "producer", "consumer",
    "constraints / allowed values", "constraints", "allowed values",
}


def _extract_h3(section_body: str, h3_prefix: str) -> Optional[str]:
    """Text under a `### Heading` within a section, up to the next `### ` or EOF.

    Operates on the body of an already-extracted `## ` section (see
    _extract_section, which preserves H3 lines). Returns None if the sub-heading
    is absent; '' if present but empty.
    """
    out: list[str] = []
    capturing = False
    found = False
    for line in section_body.splitlines():
        if line.startswith("### "):
            if capturing:
                break
            if line.strip().startswith(h3_prefix):
                capturing = True
                found = True
            continue
        if capturing:
            out.append(line)
    if not found:
        return None
    return "\n".join(out).strip()


def _is_scaffold_table_line(line: str) -> bool:
    """True for an empty Field-Dictionary skeleton row (header or separator).

    Lets `_subpart_filled` treat a bare scaffold table (header + `---` rule,
    no data rows) as unfilled, while any real data row survives.
    """
    s = line.strip()
    if not s.startswith("|"):
        return False
    cells = [c.strip().lower() for c in s.strip("|").split("|")]
    # markdown separator row: every cell is dashes / colons
    if cells and all(c and set(c) <= set("-: ") for c in cells):
        return True
    # header-template row: every non-empty cell is a known scaffold header cell
    nonempty = [c for c in cells if c]
    if nonempty and all(c in _FIELD_DICT_HEADER_CELLS for c in nonempty):
        return True
    return False


def _subpart_filled(text: str) -> bool:
    """Form-only: True if a Design & Contract sub-part has real content / N/A.

    Strips `<...>` scaffold placeholders, blank lines, and the empty
    Field-Dictionary table skeleton; anything remaining (prose, a data row, or
    an explicit `N/A — <reason>` line) counts as filled.
    """
    stripped = re.sub(r"<[^>]*>", "", text)
    for line in stripped.splitlines():
        s = line.strip()
        if not s:
            continue
        if _is_scaffold_table_line(s):
            continue
        return True
    return False


def design_contract_adequacy(body: str) -> tuple[bool, str]:
    """Form-only adequacy check for the `## Design & Contract` section.

    Returns (is_adequate, reason). Only meaningful for COMPLEX proposals — the
    caller gates with _is_complex_proposal. Verifies the section is PRESENT and
    each of its three H3 sub-parts (Interfaces·I/O·Realization / Field
    Dictionary / Flow) is filled: after dropping `<...>` placeholders each
    sub-part has real content OR an explicit `N/A — <reason>` line. FORM only —
    whether the design is *correct* is the human approver's call. Mirrors
    current_state_adequacy (P-0124).
    """
    if _DESIGN_CONTRACT_HEADING not in body:
        return False, "missing '## Design & Contract' section"
    section = _extract_section(body, _DESIGN_CONTRACT_HEADING)
    for sub in _DESIGN_CONTRACT_SUBHEADINGS:
        sub_body = _extract_h3(section, sub)
        if sub_body is None:
            return False, f"missing '{sub}' sub-heading under Design & Contract"
        if not _subpart_filled(sub_body):
            return False, (f"'{sub}' is empty or still the scaffold placeholder "
                           f"(fill it, or write 'N/A — <reason>')")
    return True, "ok"


def _count_real_phases(body: str) -> int:
    """Count `### Phase` headings whose title is not a `<...>` placeholder."""
    n = 0
    for line in body.splitlines():
        m = _PHASE_HEADING_RE.match(line)
        if not m:
            continue
        rest = m.group(1)
        title = rest.split(":", 1)[1].strip() if ":" in rest else ""
        if not title:
            continue  # bare heading, no title -> treat as placeholder
        if title.startswith("<") and title.endswith(">"):
            continue
        n += 1
    return n


def _is_complex_proposal(body: str) -> bool:
    """Structural signal for whether the design-contract gate applies.

    True iff (>=2 non-placeholder `### Phase` entries) OR (any `## Scope`
    file-token lives under `contracts/`). FORM-only. By design this does NOT
    trigger on single-phase cross-agent work — that's a deferred Open Question
    (P-0124); revisit after dogfooding.
    """
    if _count_real_phases(body) >= 2:
        return True
    for tok in _extract_scope_file_tokens(body):
        norm = tok.replace("\\", "/")
        if norm.startswith("contracts/") or "/contracts/" in norm:
            return True
    return False


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
    allow_empty_current_state: bool = False,
    allow_thin_spec: bool = False,
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
            # P-0108 G1 level-D: hard research gate. Block approve when the
            # Current State section is absent / placeholder / has no concrete
            # file reference. Same predicate as audit Check 13 (WARN). FORM
            # only — the approver judges substance.
            if not allow_empty_current_state:
                ok, reason = current_state_adequacy(body)
                if not ok:
                    raise ValueError(
                        f"Cannot approve {proposal_id}: research gate — {reason}. "
                        f"Fill '## Current State (read, not assumed)' with what the "
                        f"code/config does TODAY where you will change it (cite >=1 "
                        f"file:line you READ), or pass --allow-empty-current-state "
                        f"(justify in --note) for a legacy/greenfield case."
                    )
            # P-0124: design-contract gate. For COMPLEX proposals (>=2 phases or
            # a contracts/ scope token) block approve until the Design & Contract
            # section's three sub-parts are filled. Same predicate as audit
            # Check 14 (WARN). FORM only — the approver judges substance.
            if not allow_thin_spec and _is_complex_proposal(body):
                ok, reason = design_contract_adequacy(body)
                if not ok:
                    raise ValueError(
                        f"Cannot approve {proposal_id}: design-contract gate — {reason}. "
                        f"Fill '## Design & Contract' (Interfaces·I/O·Realization / Field "
                        f"Dictionary / Flow; use 'N/A — <reason>' where a sub-part truly "
                        f"doesn't apply), or pass --allow-thin-spec (justify in --note)."
                    )
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


def _emit_create_recall(description: str) -> None:
    """Print proposal_suggest's three-way recall (①②③) after a create.

    P-0124 makes the drafting recall automatic (was an optional step): surfaces
    ① similar proposals / ② drafting checklist & lessons / ③ likely scope owner.
    Best-effort — a recall failure WARNs but never fails `create` (the proposal
    is already written). Prefers the in-process import (proposal_suggest lives
    next to this file); falls back to shelling out to its CLI.
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # ①②③/CJK on a GBK console
    except (AttributeError, ValueError):
        pass
    try:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        import proposal_suggest as _ps
        sys.stdout.write(_ps.render(_ps.suggest(description)) + "\n")
        return
    except Exception:
        pass
    try:
        suggest_py = REPO_ROOT / "tools" / "proposal_suggest.py"
        result = subprocess.run(
            [sys.executable, str(suggest_py), description],
            capture_output=True, text=True, encoding="utf-8",
            timeout=20, cwd=REPO_ROOT,
        )
        if result.returncode == 0 and result.stdout.strip():
            sys.stdout.write(result.stdout)
            return
    except Exception:
        pass
    sys.stdout.write("[WARN] proposal_suggest recall unavailable; skipped\n")


def _cmd_create(args):
    path = create_proposal(slug=args.slug, title=args.title, agent=args.agent)
    print(f"[OK] Created {path.relative_to(REPO_ROOT.parent)}")
    fm, _ = parse_proposal(path)
    print(f"     id={fm['id']} agent={fm['agent']} status={fm['status']}")
    # P-0124: auto-emit the drafting recall so the author sees prior art /
    # checklist / scope owner without a separate opt-in step.
    _emit_create_recall(args.title)
    return 0


def _cmd_transition(args):
    path, prev, new = transition_proposal(
        args.id,
        args.to,
        note=args.note or "",
        rejection_reason=args.reason or "",
        commit_hash=args.commit or "",
        superseded_by=args.superseded_by or "",
        allow_empty_current_state=args.allow_empty_current_state,
        allow_thin_spec=args.allow_thin_spec,
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


def _cmd_reconcile(args):
    result = reconcile(args.id, args.commit)
    print(f"=== reconcile {args.id} @ {args.commit} ===")
    print(f"scope tokens ({len(result['scope_tokens'])}): "
          f"{', '.join(result['scope_tokens']) or '(none)'}")
    print(f"changed files ({len(result['changed'])}): "
          f"{', '.join(result['changed']) or '(none)'}")
    print("\n[in scope, NOT touched]")
    for t in result["in_scope_not_touched"]:
        print(f"  - {t}")
    if not result["in_scope_not_touched"]:
        print("  (none)")
    print("\n[touched, NOT in scope]")
    for c in result["touched_not_in_scope"]:
        print(f"  - {c}")
    if not result["touched_not_in_scope"]:
        print("  (none)")
    return 0


# ---------------------------------------------------------------------------
# P-0076: classify subcommand — fast-path machine classifier
# ---------------------------------------------------------------------------

_CLASSIFY_PATHS_FILE = REPO_ROOT / "tools" / "proposal-classify-paths.json"
_CLASSIFY_KEYWORDS_FILE = REPO_ROOT / "tools" / "proposal-classify-keywords.json"
_CLASSIFY_LOG = REPO_ROOT / ".claude" / "cache" / "classify_log.jsonl"


def _classify_load_paths() -> list[tuple[str, str]]:
    """Return [(category, glob), ...] for the high-sensitivity allowlist."""
    if not _CLASSIFY_PATHS_FILE.is_file():
        return []
    data = json.loads(_CLASSIFY_PATHS_FILE.read_text(encoding="utf-8"))
    return [(c, g) for c, body in data["categories"].items() for g in body["globs"]]


def _classify_load_keywords() -> list[str]:
    if not _CLASSIFY_KEYWORDS_FILE.is_file():
        return []
    data = json.loads(_CLASSIFY_KEYWORDS_FILE.read_text(encoding="utf-8"))
    return [k for k in data.get("keywords", []) if isinstance(k, str)]


def _classify_session_id() -> str:
    sid = os.environ.get("CLAUDE_SESSION_ID", "").strip()
    if sid:
        return sid
    fallback = Path.home() / ".claude" / "session_id_current.txt"
    if fallback.is_file():
        try:
            return fallback.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            return "unknown"
    return "unknown"


def _classify_quick(paths: list[str], description: str) -> dict:
    """Mechanical classifier: path allowlist + keyword regex.

    Returns {verdict, reason, matches, mode}.
    """
    sys.path.insert(0, str(REPO_ROOT / "tools"))
    from _classify_match import match

    path_globs = _classify_load_paths()
    keywords = _classify_load_keywords()

    path_hits = []
    for p in paths:
        pnorm = p.replace("\\", "/")
        if pnorm.startswith("./"):
            pnorm = pnorm[2:]
        if pnorm.startswith(str(REPO_ROOT).replace("\\", "/") + "/"):
            pnorm = pnorm[len(str(REPO_ROOT).replace("\\", "/")) + 1:]
        for cat, glob in path_globs:
            if match(pnorm, glob):
                path_hits.append({"path": pnorm, "category": cat, "glob": glob})
                break

    keyword_hits = []
    if description:
        d_lower = description.lower()
        for kw in keywords:
            if kw.lower() in d_lower:
                keyword_hits.append(kw)

    if path_hits or keyword_hits:
        reasons = []
        if path_hits:
            cats = sorted({h["category"] for h in path_hits})
            reasons.append(f"path match: {','.join(cats)}")
        if keyword_hits:
            reasons.append(f"keyword: {','.join(keyword_hits[:3])}")
        return {
            "verdict": "PROPOSAL_REQUIRED",
            "reason": "; ".join(reasons),
            "matches": {"paths": path_hits, "keywords": keyword_hits},
            "mode": "quick",
        }
    return {
        "verdict": "NO_PROPOSAL",
        "reason": "no path/keyword hit in allowlist",
        "matches": {"paths": [], "keywords": []},
        "mode": "quick",
    }


def _classify_append_log(entry: dict) -> None:
    _CLASSIFY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _CLASSIFY_LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _cmd_classify(args):
    if not args.path:
        print("[FAIL] --path required (at least one)", file=sys.stderr)
        return 1

    if args.quick:
        result = _classify_quick(args.path, args.description)
    else:
        result = {
            "verdict": "NEEDS_CLARIFICATION",
            "reason": (
                "non-quick mode requires LLM judgment — run quick mode for "
                "mechanical answer, or invoke /proposal classify <desc> "
                "skill-flow for full LLM analysis"
            ),
            "matches": {},
            "mode": "llm-deferred",
        }

    entry = {
        "ts": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session_id": _classify_session_id(),
        "agent": detect_agent(),
        "paths": [p.replace("\\", "/") for p in args.path],
        "description": args.description,
        "verdict": result["verdict"],
        "reason": result["reason"],
        "mode": result["mode"],
    }
    try:
        _classify_append_log(entry)
    except OSError as e:
        print(f"[WARN] log write failed: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"[classify] {result['verdict']}")
        print(f"reason: {result['reason']}")
        if result["matches"].get("paths"):
            for hit in result["matches"]["paths"]:
                print(f"  path: {hit['path']} -> {hit['category']}/{hit['glob']}")
        if result["matches"].get("keywords"):
            print(f"  keywords: {', '.join(result['matches']['keywords'])}")
        print(f"mode: {result['mode']}")
    return 0


# ---------------------------------------------------------------------------


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
    p.add_argument("--allow-empty-current-state", action="store_true",
                   help="Override the P-0108 research gate on --to approved "
                        "(legacy/greenfield escape hatch; justify in --note)")
    p.add_argument("--allow-thin-spec", action="store_true",
                   help="Override the P-0124 design-contract gate on --to "
                        "approved for a complex proposal (justify in --note)")
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

    p = sub.add_parser("reconcile",
                       help="As-built coverage: Scope file-tokens vs a commit's "
                            "changed files (P-0108, advisory)")
    p.add_argument("--id", required=True, help="P-NNNN")
    p.add_argument("--commit", required=True, help="Commit hash or A..B range")
    p.set_defaults(func=_cmd_reconcile)

    p = sub.add_parser("classify",
                       help="Classify Edit/Write target as NO_PROPOSAL / PROPOSAL_REQUIRED / NEEDS_CLARIFICATION (P-0076)")
    p.add_argument("--path", action="append", default=[],
                   help="Target path to classify (repeatable). Repo-relative; absolute also accepted.")
    p.add_argument("--description", default="",
                   help="Optional description (only used in non-quick LLM-prompt mode; ignored under --quick)")
    p.add_argument("--quick", action="store_true",
                   help="Machine-only classification (path allowlist + keyword regex); no LLM round trip")
    p.add_argument("--json", action="store_true",
                   help="Output JSON only (suppress human-readable line)")
    p.set_defaults(func=_cmd_classify)

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

