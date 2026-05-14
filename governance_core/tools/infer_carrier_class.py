"""Infer `carrier_class` for every entry under knowledge/ — read-only.

P-0053 Phase 3: produces `audit/knowledge_class_inference_report.md` listing
each existing knowledge MD file with its inferred class, the inference
reason, and any conflicts (file already declares carrier_class that
disagrees with the inferred value).

This tool **does not modify any source files**. Backfill of the
`carrier_class` frontmatter field is out of scope for P-0053; that work
is owned by P-0054 or a separate backfill proposal that consumes this
report as input.

Inference is path-based: top-level knowledge/ subdir -> class, with
`models/` split by filename (*_current.md -> current-state, others ->
reference). The mapping is shared with `tools/audit_knowledge.py` so
inference here cannot drift from auditor expectations.

Usage:
    python tools/infer_carrier_class.py
    python tools/infer_carrier_class.py --out audit/custom_report.md
    python tools/infer_carrier_class.py --root ../agent-rules     # other clone
"""

import argparse
import logging
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
if str(DEFAULT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT))
if str(DEFAULT_ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(DEFAULT_ROOT / "tools"))

# Reuse the audit-driven helpers so the two tools stay in lockstep.
from audit_knowledge import (  # noqa: E402
    CARRIER_CLASS_PATH_MAP,
    SKIP_FILENAMES,
    _expected_carrier_class,
    parse_frontmatter,
)


def _inference_reason(rel: Path, inferred: str | None) -> str:
    """Human-readable explanation for the inferred class."""
    if inferred is None:
        top = rel.parts[0] if rel.parts else "<empty>"
        return f"top-dir {top!r} has no mapping in CARRIER_CLASS_PATH_MAP"
    top = rel.parts[0]
    if top == "models":
        if rel.name.endswith("_current.md"):
            return "models/ + filename ends with _current.md -> current-state"
        return f"models/ + filename {rel.name!r} (not _current.md) -> reference"
    return f"top-dir {top!r} -> {inferred}"


def infer(root: Path) -> dict:
    """Walk knowledge/ and return a structured inference dict."""
    knowledge = root / "knowledge"
    if not knowledge.is_dir():
        raise FileNotFoundError(f"knowledge/ not found at {knowledge}")

    md_files = sorted(
        p for p in knowledge.rglob("*.md")
        if p.name not in SKIP_FILENAMES
    )

    entries = []
    class_counts: Counter = Counter()
    by_class: dict[str, list[Path]] = defaultdict(list)
    unmapped: list[Path] = []
    declared_conflicts: list[tuple[Path, str, str]] = []
    declared_matches: list[Path] = []

    for f in md_files:
        rel = f.relative_to(knowledge)
        inferred = _expected_carrier_class(rel)
        reason = _inference_reason(rel, inferred)

        declared: str | None = None
        try:
            text = f.read_text(encoding="utf-8")
            fm = parse_frontmatter(text)
            if fm and "carrier_class" in fm:
                declared = fm["carrier_class"]
        except Exception as exc:
            logger.warning("  could not parse %s: %s", rel, exc)

        if inferred is None:
            unmapped.append(rel)
        else:
            class_counts[inferred] += 1
            by_class[inferred].append(rel)

        if declared is not None:
            if declared == inferred:
                declared_matches.append(rel)
            else:
                declared_conflicts.append((rel, declared, inferred or "<none>"))

        entries.append({
            "rel": rel,
            "inferred": inferred,
            "reason": reason,
            "declared": declared,
        })

    return {
        "total": len(md_files),
        "entries": entries,
        "class_counts": class_counts,
        "by_class": by_class,
        "unmapped": unmapped,
        "declared_conflicts": declared_conflicts,
        "declared_matches": declared_matches,
    }


def render_report(result: dict, generated_at: str) -> str:
    """Build the markdown report body."""
    lines: list[str] = []
    lines.append("# Knowledge Carrier-Class Inference Report")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append(f"Source: knowledge/")
    lines.append(f"Total entries: {result['total']}")
    lines.append(f"Tool: tools/infer_carrier_class.py (P-0053 Phase 3, read-only)")
    lines.append("")
    lines.append("> **This report is read-only**. It does not modify any source")
    lines.append("> file. Backfilling `carrier_class` frontmatter is owned by")
    lines.append("> P-0054 (HTML profile + autogen) or a separate backfill")
    lines.append("> proposal. Use this report as the input plan.")
    lines.append("")

    # --- Summary ---
    lines.append("## 1. Summary by inferred class")
    lines.append("")
    lines.append("| Class | Count |")
    lines.append("|-------|-------|")
    for cls in sorted(result["class_counts"]):
        lines.append(f"| `{cls}` | {result['class_counts'][cls]} |")
    if result["unmapped"]:
        lines.append(f"| _(unmapped — needs governance review)_ | {len(result['unmapped'])} |")
    lines.append(f"| **Total** | **{result['total']}** |")
    lines.append("")

    # --- Unmapped ---
    if result["unmapped"]:
        lines.append("## 2. Unmapped entries (governance gap)")
        lines.append("")
        lines.append("Files in `knowledge/` subdirectories that have no entry")
        lines.append("in `CARRIER_CLASS_PATH_MAP` (i.e., `knowledge/governance/`")
        lines.append("`knowledge-carrier-classes.md` §3 mapping is missing this")
        lines.append("subdirectory). Resolve before P-0054 backfill: either add")
        lines.append("the subdirectory to the path map (governance doc + audit")
        lines.append("code) or reclassify the file out of this subdirectory.")
        lines.append("")
        for rel in result["unmapped"]:
            lines.append(f"- `{rel.as_posix()}`")
        lines.append("")
    else:
        lines.append("## 2. Unmapped entries")
        lines.append("")
        lines.append("_None — every entry's top-level subdirectory is mapped._")
        lines.append("")

    # --- Declared conflicts ---
    lines.append("## 3. Declared-vs-inferred conflicts")
    lines.append("")
    if result["declared_conflicts"]:
        lines.append("Files that already declare `carrier_class` in their")
        lines.append("frontmatter but whose value disagrees with the inferred")
        lines.append("class. Each row requires a human decision: either the")
        lines.append("declaration is wrong (typo / outdated) and should be")
        lines.append("changed to the inferred value, or the file is in the")
        lines.append("wrong subdirectory and should be moved.")
        lines.append("")
        lines.append("| File | Declared | Inferred |")
        lines.append("|------|----------|----------|")
        for rel, declared, inferred in result["declared_conflicts"]:
            lines.append(f"| `{rel.as_posix()}` | `{declared}` | `{inferred}` |")
        lines.append("")
    else:
        lines.append("_None — no entry yet declares a conflicting `carrier_class`._")
        lines.append("")

    # --- Declared matches (Phase 2 happy path) ---
    lines.append("## 4. Entries already self-declaring (Phase 2 self-conforming)")
    lines.append("")
    if result["declared_matches"]:
        for rel in result["declared_matches"]:
            lines.append(f"- `{rel.as_posix()}`")
        lines.append("")
    else:
        lines.append("_None._")
        lines.append("")

    # --- Per-class manifests ---
    lines.append("## 5. Inferred-class manifests (planned backfill targets)")
    lines.append("")
    lines.append("Each subsection lists the files that should receive that")
    lines.append("`carrier_class: <value>` line in their frontmatter when the")
    lines.append("backfill phase runs.")
    lines.append("")
    for cls in sorted(result["by_class"]):
        files = result["by_class"][cls]
        lines.append(f"### 5.{sorted(result['by_class']).index(cls) + 1} `{cls}` — {len(files)} entries")
        lines.append("")
        for rel in files:
            lines.append(f"- `{rel.as_posix()}`")
        lines.append("")

    # --- Suggested next steps ---
    lines.append("## 6. Suggested next steps")
    lines.append("")
    lines.append("1. **Resolve unmapped subdirectories** (§2): add to")
    lines.append("   `knowledge/governance/knowledge-carrier-classes.md` §3")
    lines.append("   path table and to `tools/audit_knowledge.py`")
    lines.append("   `CARRIER_CLASS_PATH_MAP`.")
    lines.append("2. **Resolve declared conflicts** (§3): fix per-file.")
    lines.append("3. **Plan backfill PR** based on §5 manifests; the field")
    lines.append("   is `carrier_class: <value>` inserted after `owner:` in")
    lines.append("   each entry's frontmatter.")
    lines.append("4. **Once backfill ships**, bump schema to v1.3.0 and flip")
    lines.append("   Checks 12-15 from warn to fail (see schema §8.2).")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Infer carrier_class for knowledge/ entries (read-only)")
    parser.add_argument("--root", type=str, default=None, help="Project root (default: this script's repo)")
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output report path (default: audit/knowledge_class_inference_report.md under --root)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT
    out_path = (
        Path(args.out).resolve()
        if args.out
        else root / "audit" / "knowledge_class_inference_report.md"
    )

    try:
        result = infer(root)
    except FileNotFoundError as exc:
        logger.error("[FATAL] %s", exc)
        return 1

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = render_report(result, generated_at)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    logger.info("[OK] wrote %s", out_path)
    logger.info(
        "     total=%d unmapped=%d declared_conflicts=%d declared_matches=%d",
        result["total"],
        len(result["unmapped"]),
        len(result["declared_conflicts"]),
        len(result["declared_matches"]),
    )
    for cls in sorted(result["class_counts"]):
        logger.info("     %-20s %d", cls, result["class_counts"][cls])

    # P-0053 Phase 3 is read-only; always return 0. Unmapped / conflicts
    # are governance signals for the user, not auditor failures.
    return 0


if __name__ == "__main__":
    sys.exit(main())
