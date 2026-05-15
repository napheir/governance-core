"""Migrate legacy proposals/*.md to v1.1.0 storage scheme (P-0001 Phase 3).

Dry-run by default; pass --execute to actually move files. Output is a
JSON-line report that's safe to commit alongside the migration commit.

Migration rules (per P-0001 Phase 4 plan):
  - Terminal proposals (implemented / rejected / superseded) →
    move to proposals/_archive/<YYYY>/p-NNNN-<slug>.md (in git)
  - In-flight proposals (draft / pending / approved / in-progress) →
    move to shared_state/proposals/<inferred-agent>/p-NNNN-<slug>.md
  - Proposals lacking frontmatter → flag as REQUIRES_BACKFILL (Phase 4
    judgment call: user decides keep-as-legacy / backfill-and-migrate /
    archive-as-orphaned)

ID allocation:
  Each migrated proposal gets a fresh p-NNNN- prefix allocated via the
  same lock-protected mechanism as `/proposal create`. The original
  filename slug is preserved (lowercased, non-alphanumeric → underscore).
  P-0001 is already grandfathered.

Agent inference heuristic:
  - frontmatter `owner` field if present → that agent
  - body keyword scan: count agent name hits in first 2000 chars
  - title/filename keyword: rules/trade/data/research → respective agent
  - default → core (when ambiguous)

Output:
  - stdout: JSON-line report per proposal (action, src, dst, agent, reason)
  - stderr: summary (counts per action)
  - exit 0 always for dry-run; --execute exits 0 on full success / 1 on
    any failure during move (atomicity not guaranteed across multiple files;
    failure leaves partial state)

Usage:
    python tools/migrate_proposals_to_shared_state.py
    python tools/migrate_proposals_to_shared_state.py --execute
    python tools/migrate_proposals_to_shared_state.py --filter status=implemented
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import load_proposals_config  # noqa: E402
from tools.proposal_lib import (  # noqa: E402
    _FILENAME_ID_RE, allocate_next_id, parse_proposal,
    TERMINAL_STATUS, write_atomic, _agents,
)

LEGACY_ROOT = REPO_ROOT / "proposals"


def _infer_agent(filename: str, fm: dict, body: str) -> tuple[str, str]:
    """Best-effort owner agent inference.

    Returns (agent, reason).
    """
    if "owner" in fm and fm["owner"] in _agents():
        return fm["owner"], f"frontmatter owner={fm['owner']}"
    if "agent" in fm and fm["agent"] in _agents():
        return fm["agent"], f"frontmatter agent={fm['agent']}"

    # Score-based heuristic on first 2000 chars + filename
    text = (filename + "\n" + body[:2000]).lower()
    scores = {}
    keywords = {
        "rules": ["rules-agent", "rules clone", "rules/", "rules scope",
                  "agent-rules", "feature/rules"],
        "trade": ["trade-agent", "trade clone", "trade/", "trade scope",
                  "agent-trade", "feature/trade", "futu paper", "futu live"],
        "data": ["data-agent", "data clone", "data/", "data scope",
                 "agent-data", "feature/data", "sync_positions"],
        "research": ["research-agent", "research/", "agent-research",
                     "feature/research", "research scope"],
    }
    for agent, kws in keywords.items():
        scores[agent] = sum(text.count(kw) for kw in kws)
    top = max(scores, key=scores.get)
    if scores[top] >= 2:
        return top, f"keyword score {top}={scores[top]} (others={scores})"
    return "core", f"default (low keyword signal: {scores})"


def _slug_from_filename(name: str) -> str:
    """Convert legacy filename (without `.md`) to v1.1.0-safe slug."""
    stem = name[:-3] if name.endswith(".md") else name
    # If already has p-NNNN- prefix, strip it
    stem = re.sub(r"^p-\d{4,}-", "", stem)
    # Lowercase + non-alphanumeric → underscore
    slug = re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")
    if not slug:
        slug = "untitled"
    return slug


def _enumerate_legacy() -> list[Path]:
    """Top-level proposals/*.md, excluding _*.md and templates/."""
    files = []
    for p in sorted(LEGACY_ROOT.glob("*.md")):
        if not p.is_file():
            continue
        if p.name.startswith("_"):
            continue
        files.append(p)
    return files


def _plan_migration(path: Path, used_ids: set) -> dict:
    """Decide migration action for a single legacy file.

    Returns plan dict:
      {action, src, dst (or None), agent, reason, status, requires_backfill}
    """
    try:
        fm, body = parse_proposal(path)
    except (OSError, ValueError) as e:
        return {
            "action": "REQUIRES_BACKFILL",
            "src": str(path.relative_to(REPO_ROOT)),
            "reason": f"parse failed: {e}",
        }

    status = fm.get("status", "pending")

    # Already new-scheme filename?
    file_m = _FILENAME_ID_RE.match(path.name)
    if file_m:
        # Already has p-NNNN-, keep that ID. Allocate marker so we don't dup.
        nnnn = int(file_m.group(1))
        used_ids.add(nnnn)
        proposal_id = f"P-{nnnn:04d}"
        slug = _slug_from_filename(path.name)
    else:
        # Allocate fresh ID (deferred to execute path so dry-run output is stable).
        proposal_id = "P-PENDING"  # placeholder; resolved in --execute
        slug = _slug_from_filename(path.name)

    agent, reason = _infer_agent(path.name, fm, body)

    if status in TERMINAL_STATUS:
        target_dir = REPO_ROOT / "proposals" / "_archive" / _year_for(fm, status)
        action = "ARCHIVE"
    elif status in {"draft", "pending", "approved", "in-progress"}:
        # P-0059 Phase 2.3d: prefer .governance/config.json's shared_state_root;
        # fall back to relative "../shared_state/proposals" if config missing.
        shared_state_root = None
        try:
            import json
            cfg_path = REPO_ROOT / ".governance" / "config.json"
            if cfg_path.exists():
                cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                if cfg.get("shared_state_root"):
                    shared_state_root = Path(cfg["shared_state_root"])
        except Exception:
            pass
        if shared_state_root is None:
            target_dir = REPO_ROOT / "../shared_state/proposals" / agent
        else:
            target_dir = shared_state_root / "proposals" / agent
        action = "MOVE_TO_INFLIGHT"
    else:
        return {
            "action": "REQUIRES_BACKFILL",
            "src": str(path.relative_to(REPO_ROOT)),
            "reason": f"unknown status {status!r}",
        }

    dst_filename = f"p-{(proposal_id.split('-')[1] if proposal_id != 'P-PENDING' else 'XXXX')}-{slug}.md"
    return {
        "action": action,
        "src": str(path.relative_to(REPO_ROOT)),
        "dst": str((target_dir / dst_filename).resolve()),
        "agent": agent,
        "agent_reason": reason,
        "status": status,
        "proposal_id": proposal_id,
        "requires_id_allocation": proposal_id == "P-PENDING",
    }


def _year_for(fm: dict, status: str) -> str:
    """Year for archive subdir from terminal-state date field."""
    date_field = {
        "implemented": "implemented_at",
        "rejected": "rejected_at",
        "superseded": "approved_at",
    }.get(status, "created")
    date_str = fm.get(date_field, fm.get("created", ""))
    if re.match(r"^\d{4}-", date_str):
        return date_str[:4]
    return "unknown"


def _execute_one(plan: dict) -> tuple[bool, str]:
    """Move file per plan. Returns (success, message)."""
    src = Path(plan["src"])
    if not src.is_absolute():
        src = REPO_ROOT / src

    if plan.get("requires_id_allocation"):
        new_id = allocate_next_id()
        plan["proposal_id"] = new_id
        nnnn = new_id.split("-")[1]
        # Re-derive dst with allocated nnnn
        plan["dst"] = plan["dst"].replace("p-XXXX-", f"p-{nnnn}-")

    dst = Path(plan["dst"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return False, f"dst exists: {dst}"

    # Read, optionally upgrade frontmatter (add id/agent), atomically write dst
    text = src.read_text(encoding="utf-8")
    try:
        fm, body = parse_proposal(src)
    except ValueError as e:
        return False, f"parse src failed: {e}"
    if "id" not in fm:
        fm["id"] = plan["proposal_id"]
    if "agent" not in fm:
        fm["agent"] = plan["agent"]
    # Re-serialize via simple key:val (avoid reordering legacy fm fields drastically)
    from tools.proposal_lib import serialize_frontmatter
    new_text = serialize_frontmatter(fm) + "\n" + body.lstrip("\n")
    write_atomic(dst, new_text)
    src.unlink()
    return True, f"moved {src.name} -> {dst}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--execute", action="store_true",
                        help="Actually move files (default: dry-run)")
    parser.add_argument("--filter", default="",
                        help="key=value filter (e.g. status=implemented)")
    args = parser.parse_args()

    files = _enumerate_legacy()
    if not files:
        print("[INFO] no legacy proposals found in proposals/*.md", file=sys.stderr)
        return 0

    used_ids: set = set()
    plans = []
    for f in files:
        plan = _plan_migration(f, used_ids)
        plans.append(plan)

    # Apply --filter
    if args.filter and "=" in args.filter:
        k, v = args.filter.split("=", 1)
        plans = [p for p in plans if p.get(k) == v]

    # Output JSON-line report
    for p in plans:
        print(json.dumps(p, ensure_ascii=False))

    # Summary to stderr
    counts = {}
    for p in plans:
        counts[p["action"]] = counts.get(p["action"], 0) + 1
    print("\n=== Migration plan summary ===", file=sys.stderr)
    for action, n in sorted(counts.items()):
        print(f"  {action}: {n}", file=sys.stderr)
    print(f"  TOTAL: {len(plans)}", file=sys.stderr)
    print(f"  Mode: {'EXECUTE' if args.execute else 'DRY-RUN (use --execute)'}",
          file=sys.stderr)

    if not args.execute:
        return 0

    # Execute path
    fail_count = 0
    for plan in plans:
        if plan["action"] == "REQUIRES_BACKFILL":
            print(f"[SKIP] {plan['src']} requires backfill: {plan.get('reason', '')}",
                  file=sys.stderr)
            continue
        ok, msg = _execute_one(plan)
        if ok:
            print(f"[OK] {msg}", file=sys.stderr)
        else:
            print(f"[FAIL] {plan['src']}: {msg}", file=sys.stderr)
            fail_count += 1
    return 1 if fail_count else 0


if __name__ == "__main__":
    sys.exit(main())
