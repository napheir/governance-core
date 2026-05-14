# -*- coding: utf-8 -*-
"""STATE.md rotation: move entries older than N days to STATE_ARCHIVE.md.

Keeps STATE.md as a lean rolling window (default 7 days) while preserving
full history in STATE_ARCHIVE.md for traceability.

Usage:
    python tools/rotate_state.py              # dry-run (show what would move)
    python tools/rotate_state.py --execute    # perform rotation
    python tools/rotate_state.py --days 14    # custom window

Rules:
  - STATE.md header (lines before first ### entry) is always preserved
  - Entries are identified by "### YYYY-MM-DD" pattern
  - Entries within the rolling window stay in STATE.md
  - Older entries are prepended to STATE_ARCHIVE.md (newest-first order)
  - STATE_ARCHIVE.md is created if it doesn't exist
"""
import argparse
import logging
import re
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

_ENTRY_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2})")

ARCHIVE_HEADER = """# Trade Agent 项目状态文档 — Archive

> 此文件包含 STATE.md 的历史条目（超出滚动窗口的部分）。
> 按时间倒序排列（最新在前）。
> 由 `tools/rotate_state.py` 自动管理。

---

"""


def parse_entries(content: str) -> tuple[str, list[tuple[str, str, list[str]]]]:
    """Parse STATE.md into header and dated entries.

    Args:
        content: Full STATE.md content.

    Returns:
        Tuple of (header_text, entries) where each entry is
        (date_str, heading_line, body_lines).
    """
    lines = content.split("\n")
    header_lines = []
    entries = []
    current_entry = None

    for line in lines:
        match = _ENTRY_RE.match(line)
        if match:
            if current_entry:
                entries.append(current_entry)
            current_entry = (match.group(1), line, [])
        elif current_entry:
            current_entry[2].append(line)
        else:
            header_lines.append(line)

    if current_entry:
        entries.append(current_entry)

    header = "\n".join(header_lines)
    return header, entries


def rotate(
    days: int = 7,
    max_per_day: int = 3,
    execute: bool = False,
    root: Path | None = None,
) -> dict:
    """Rotate old entries from STATE.md to STATE_ARCHIVE.md.

    Two cuts apply, both archive overflow into STATE_ARCHIVE.md:
      1. Date window: entries with date < today-`days` go to archive.
      2. Per-day cap: within the kept window, if a single date has more
         than `max_per_day` entries, the oldest of that day are archived
         (newest `max_per_day` stay). Solves the "5 wrap-ups in one day
         each adding a 50-line entry" bloat that the date window alone
         can't catch — the window doesn't trim today.

    Args:
        days: Rolling window size in days.
        max_per_day: Max entries kept per date within the window.
                     Set to 0 to disable per-day capping.
        execute: If True, write changes. If False, dry-run only.
        root: Project root directory containing STATE.md.

    Returns:
        Dict with rotation statistics.
    """
    project_root = root or DEFAULT_ROOT
    state_file = project_root / "STATE.md"
    archive_file = project_root / "STATE_ARCHIVE.md"

    if not state_file.exists():
        return {"error": "STATE.md not found"}

    content = state_file.read_text(encoding="utf-8")
    header, entries = parse_entries(content)

    cutoff = date.today() - timedelta(days=days)
    keep = []
    archive = []

    # Pass 1: date window cut.
    for date_str, heading, body in entries:
        try:
            entry_date = date.fromisoformat(date_str)
        except ValueError:
            keep.append((date_str, heading, body))
            continue

        if entry_date >= cutoff:
            keep.append((date_str, heading, body))
        else:
            archive.append((date_str, heading, body))

    # Pass 2: per-day cap. STATE.md is appended newest-first within a day,
    # so iterate keep and demote old-of-day to archive when count exceeds.
    capped_overflow = 0
    if max_per_day > 0 and keep:
        seen_per_day: dict[str, int] = {}
        kept_after_cap = []
        for date_str, heading, body in keep:
            count = seen_per_day.get(date_str, 0)
            if count < max_per_day:
                kept_after_cap.append((date_str, heading, body))
                seen_per_day[date_str] = count + 1
            else:
                archive.append((date_str, heading, body))
                capped_overflow += 1
        keep = kept_after_cap

    stats = {
        "total_entries": len(entries),
        "keep": len(keep),
        "archive": len(archive),
        "cutoff_date": cutoff.isoformat(),
        "max_per_day": max_per_day,
        "capped_overflow": capped_overflow,
        "oldest_kept": keep[-1][0] if keep else None,
        "newest_archived": archive[0][0] if archive else None,
    }

    if not archive:
        stats["action"] = "nothing to rotate"
        return stats

    if not execute:
        stats["action"] = "dry-run (use --execute to apply)"
        return stats

    # Build new STATE.md (header + kept entries)
    new_state_parts = [header]
    for date_str, heading, body in keep:
        new_state_parts.append(heading)
        new_state_parts.extend(body)
    new_state = "\n".join(new_state_parts)

    # Build archive content
    archive_parts = []
    for date_str, heading, body in archive:
        archive_parts.append(heading)
        archive_parts.extend(body)
    archive_content = "\n".join(archive_parts)

    # Merge with existing archive if it exists
    if archive_file.exists():
        existing_archive = archive_file.read_text(encoding="utf-8")
        # Insert new archive entries after the header
        if "---\n" in existing_archive:
            # Find end of archive header (after the --- separator)
            header_end = existing_archive.index("---\n") + 4
            merged = (
                existing_archive[:header_end]
                + "\n"
                + archive_content
                + "\n"
                + existing_archive[header_end:]
            )
        else:
            merged = existing_archive + "\n" + archive_content
    else:
        merged = ARCHIVE_HEADER + archive_content + "\n"

    # Write files
    state_file.write_text(new_state, encoding="utf-8")
    archive_file.write_text(merged, encoding="utf-8")

    stats["action"] = "rotated"
    stats["state_lines"] = len(new_state.split("\n"))
    stats["archive_lines"] = len(merged.split("\n"))
    return stats


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="STATE.md Rotation")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Rolling window size in days (default: 7)",
    )
    parser.add_argument(
        "--max-per-day",
        type=int,
        default=3,
        help="Max entries kept per date within the window (default: 3, 0=disable)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform rotation (default: dry-run)",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=None,
        help="Project root containing STATE.md (default: agent-core)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else None
    stats = rotate(
        days=args.days,
        max_per_day=args.max_per_day,
        execute=args.execute,
        root=root,
    )

    print("STATE.md Rotation")
    print("=" * 40)
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
