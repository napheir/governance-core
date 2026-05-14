"""Migrate knowledge/**/*.md entries to knowledge_frontmatter_schema v1.0.0.

Two independent actions:

  1. Add the new required `owner` field to any entry whose frontmatter is
     missing it. Owner inferred from category via `knowledge/INDEX.md`'s
     Subdirectory Overview table (contracts/knowledge_index_schema.md §2.1).

  2. With `--scaffold-missing-fm`, scaffold a minimal frontmatter block on
     files that have no frontmatter at all. title from first `# Heading`,
     created/updated from git history, status=active, tags=[], owner from
     category map.

For multi-owner categories, uses the first listed owner as the default
primary owner (per frontmatter_schema §3.2). Human review may post-adjust.

Does NOT rewrite existing valid frontmatter. Does NOT touch fields other
than owner (in owner-only mode). Does NOT modify INDEX.md / _TEMPLATE.md
/ VALIDATION_TEST.md.

Usage:
    python tools/migrate_knowledge_frontmatter.py                          # dry-run, owner-only
    python tools/migrate_knowledge_frontmatter.py --execute                # apply owner-only
    python tools/migrate_knowledge_frontmatter.py --scaffold-missing-fm    # dry-run, scaffold + owner
    python tools/migrate_knowledge_frontmatter.py --scaffold-missing-fm --execute
    python tools/migrate_knowledge_frontmatter.py --root ../agent-data --execute
"""
import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

VALID_OWNERS = {"rules", "trade", "data", "research", "core"}
SKIP_FILENAMES = {"INDEX.md", "_TEMPLATE.md", "VALIDATION_TEST.md"}

FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
OWNER_LINE_RE = re.compile(r"^owner\s*:\s*(\S+)\s*$", re.MULTILINE)
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")


def parse_category_owner_map(knowledge_root: Path) -> dict[str, str]:
    """Parse top INDEX.md to build category -> primary_owner map.

    Looks for a markdown table whose header contains 'Subdirectory' and
    'Owner'. Returns {category_name: primary_owner} where primary_owner is
    the first owner listed if multi-owner.
    """
    index_md = knowledge_root / "INDEX.md"
    if not index_md.is_file():
        raise FileNotFoundError(f"top INDEX.md not found at {index_md}")
    text = index_md.read_text(encoding="utf-8")
    header_cols: list[str] | None = None
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = TABLE_ROW_RE.match(line)
        if not match:
            if header_cols is not None:
                break
            continue
        cells = [c.strip() for c in match.group(1).split("|")]
        if header_cols is None:
            normalized = [c.lower() for c in cells]
            if "subdirectory" in normalized and "owner" in normalized:
                header_cols = normalized
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header_cols, cells))
        cat = ""
        if "subdirectory" in row:
            cat = row["subdirectory"].strip("`/ ")
        owner_cell = ""
        if "owner" in row:
            owner_cell = row["owner"]
        if not cat or not owner_cell:
            continue
        primary = owner_cell.split("+")[0].strip().lower()
        if primary not in VALID_OWNERS:
            logger.warning(
                "top INDEX category %r has unrecognized primary owner %r; skipping",
                cat, primary,
            )
            continue
        result[cat] = primary
    return result


def infer_category(file_rel: Path) -> str:
    """Return top-level category name for a knowledge file.

    e.g. knowledge/experiments/EXP-X.md  -> 'experiments'
         knowledge/research/inspiration/foo.md -> 'research'
    """
    parts = file_rel.parts
    return parts[0] if parts else ""


def extract_frontmatter(text: str) -> tuple[str, str, str]:
    """Return (frontmatter_block, body, original_closing_crlf) or ('','text','').

    Keeps the closing newline style the original file used.
    """
    match = FRONTMATTER_RE.match(text)
    if not match:
        return "", text, ""
    end = match.end()
    return match.group(1), text[end:], ""


def owner_already_set(frontmatter: str) -> bool:
    """True if frontmatter has a valid `owner: <enum>` line."""
    match = OWNER_LINE_RE.search(frontmatter)
    if not match:
        return False
    return match.group(1).lower() in VALID_OWNERS


def inject_owner(frontmatter: str, owner: str) -> str:
    """Return new frontmatter with `owner: <value>` added.

    Insert after `updated:` if present, else after `created:`, else at the
    end of the frontmatter block. Preserves existing field order.
    """
    new_line = f"owner: {owner}"
    for anchor in ("updated", "created", "status", "title"):
        pattern = re.compile(rf"^({anchor}\s*:.*)$", re.MULTILINE)
        replaced = pattern.subn(lambda m: m.group(1) + "\n" + new_line, frontmatter, count=1)
        if replaced[1] > 0:
            return replaced[0]
    return frontmatter.rstrip() + "\n" + new_line


FIRST_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def git_date_bounds(repo_root: Path, file_path: Path) -> tuple[str, str]:
    """Return (created_date, updated_date) from git log for this file.

    created = date of the first commit that introduced this file.
    updated = date of the most recent commit touching this file.
    Dates are ISO 8601 YYYY-MM-DD.

    Falls back to ("", "") if the file isn't tracked or git fails.
    """
    rel = str(file_path.relative_to(repo_root))
    try:
        result = subprocess.run(
            ["git", "log", "--follow", "--format=%ad", "--date=short",
             "--", rel],
            cwd=repo_root, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.SubprocessError, OSError):
        return "", ""
    if result.returncode != 0:
        return "", ""
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        return "", ""
    return lines[-1], lines[0]  # reverse chronological -> oldest last


def scaffold_frontmatter(
    file_path: Path,
    body: str,
    owner: str,
    repo_root: Path,
) -> str:
    """Build a minimal frontmatter block for a file that has none.

    title from first `# Heading`; created/updated from git log; status=active;
    tags empty; owner from caller. Writes the new text to file_path.
    """
    title_match = FIRST_HEADING_RE.search(body)
    if title_match:
        title = title_match.group(1).strip()
    else:
        title = file_path.stem.replace("_", " ").replace("-", " ")

    created, updated = git_date_bounds(repo_root, file_path)
    if not created:
        created = "unknown"
    if not updated:
        updated = created

    return (
        "---\n"
        f"title: {title}\n"
        "status: active\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        f"owner: {owner}\n"
        "tags: []\n"
        "---\n"
    )


def migrate_file(
    file_path: Path,
    knowledge_root: Path,
    repo_root: Path,
    owner_map: dict[str, str],
    dry_run: bool,
    scaffold: bool,
) -> str:
    """Process one file; return status string."""
    rel = file_path.relative_to(knowledge_root)
    category = infer_category(rel)
    if category not in owner_map:
        return f"  [SKIP] {rel} -- category {category!r} not in INDEX owner map"

    expected_owner = owner_map[category]
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"  [FAIL] {rel} -- read error: {exc}"

    fm, body, _ = extract_frontmatter(text)

    if not fm:
        if not scaffold:
            return f"  [FAIL] {rel} -- no frontmatter (run with --scaffold-missing-fm to scaffold)"
        new_fm_block = scaffold_frontmatter(file_path, body, expected_owner, repo_root)
        new_text = new_fm_block + body.lstrip("\n")
        if dry_run:
            return f"  [NEW]  {rel} -- would scaffold frontmatter (owner: {expected_owner})"
        file_path.write_text(new_text, encoding="utf-8")
        return f"  [NEW]  {rel} -- scaffolded frontmatter (owner: {expected_owner})"

    if owner_already_set(fm):
        current = OWNER_LINE_RE.search(fm).group(1).lower()
        return f"  [OK]   {rel} -- owner already {current!r}"

    new_fm = inject_owner(fm, expected_owner)
    new_text = f"---\n{new_fm}\n---\n{body}"

    if dry_run:
        return f"  [ADD]  {rel} -- would add owner: {expected_owner}"

    file_path.write_text(new_text, encoding="utf-8")
    return f"  [ADD]  {rel} -- added owner: {expected_owner}"


def main() -> int:
    """CLI entry."""
    parser = argparse.ArgumentParser(
        description="Migrate knowledge/**/*.md to frontmatter schema v1.0.0"
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Repo root (default: agent-core)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes (default: dry-run)",
    )
    parser.add_argument(
        "--scaffold-missing-fm",
        action="store_true",
        help="Scaffold frontmatter for files that have none (default: fail on such files)",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    knowledge_root = root / "knowledge"
    if not knowledge_root.is_dir():
        logger.error("[FATAL] knowledge/ not found at %s", knowledge_root)
        return 1

    owner_map = parse_category_owner_map(knowledge_root)
    logger.info("Category owner map from %s/INDEX.md:", knowledge_root.relative_to(root))
    for cat, owner in sorted(owner_map.items()):
        logger.info("  %-16s -> %s", cat, owner)
    logger.info("")

    logger.info("Mode: %s", "EXECUTE" if args.execute else "DRY-RUN")
    logger.info("")

    added = 0
    scaffolded = 0
    already = 0
    failed = 0
    skipped = 0

    for md_path in sorted(knowledge_root.rglob("*.md")):
        if md_path.name in SKIP_FILENAMES:
            continue
        result = migrate_file(
            md_path, knowledge_root, root, owner_map,
            dry_run=not args.execute,
            scaffold=args.scaffold_missing_fm,
        )
        logger.info(result)
        if "[ADD]" in result:
            added += 1
        elif "[NEW]" in result:
            scaffolded += 1
        elif "[OK]" in result:
            already += 1
        elif "[FAIL]" in result:
            failed += 1
        elif "[SKIP]" in result:
            skipped += 1

    logger.info("")
    logger.info("=" * 50)
    logger.info("  Owner added:       %d", added)
    logger.info("  Frontmatter new:   %d", scaffolded)
    logger.info("  Already compliant: %d", already)
    logger.info("  Skipped:           %d", skipped)
    logger.info("  Failed:            %d", failed)
    logger.info("=" * 50)

    if failed > 0:
        logger.error("ACTION REQUIRED: resolve failures before re-running with --execute")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
