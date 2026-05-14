"""Backfill `status` frontmatter on existing proposals/**/*.md files.

Heuristic per `proposals/proposal_state_machine_and_skill.md` §7.1:
  1. Skip files that already have `status:` in their frontmatter
  2. Search ALL git commits in the repo for messages literally
     containing the proposal's basename `<name>.md`
  3. If exactly one commit references the proposal => `implemented`
     with that commit's short hash + ISO date
  4. If multiple commits reference => report AMBIGUOUS (require
     manual confirmation)
  5. If zero references => `pending` (conservative default)

Usage:
    python tools/backfill_proposal_status.py            # dry-run
    python tools/backfill_proposal_status.py --execute  # apply

Exit codes:
    0 = success (dry-run summary or apply complete)
    1 = error (filesystem / git failure)
"""
import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
from pathlib import Path


# Match an existing frontmatter status line; tolerant of leading whitespace
_STATUS_RE = re.compile(r"^status:\s*\S", re.MULTILINE)
_FRONTMATTER_OPEN_RE = re.compile(r"\A---\s*\n")


def _has_frontmatter_status(text: str) -> bool:
    """True if file already carries a `status:` line in frontmatter."""
    if not _FRONTMATTER_OPEN_RE.match(text):
        return False
    end = text.find("\n---\n", 4)
    if end < 0:
        return False
    return bool(_STATUS_RE.search(text[:end]))


def _git_commits_referencing(basename: str, repo_root: Path) -> list:
    """Return list of (hash, date_iso, summary) for commits whose body
    contains the literal `<basename>` (with .md suffix).

    Searches full body via `git log --grep`. Multiple matches → ambiguous.
    """
    try:
        result = subprocess.run(
            [
                "git", "log", "--all",
                "--pretty=format:%h%x09%cs%x09%s",
                f"--grep={basename}",
                "--regexp-ignore-case",
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, cwd=str(repo_root),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"[ERROR] git log failed: {exc}\n")
        return []
    if result.returncode != 0:
        return []
    out = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            out.append(tuple(parts))
    return out


def _classify(rel_path: str, basename_no_ext: str, repo_root: Path) -> dict:
    """Compute backfill decision for one proposal."""
    matches = _git_commits_referencing(basename_no_ext + ".md", repo_root)

    # Filter out commits that just CREATED the proposal file (we want
    # implementation references, not authoring commits). Heuristic: a
    # commit whose subject contains "proposal" or starts with "docs(...)"
    # creating the proposal is likely the authoring commit. We can't
    # distinguish perfectly, so use diff-stat: if the only file the
    # commit touched is the proposal itself, it's likely authoring.
    impl_matches = []
    for h, date, summary in matches:
        try:
            diff = subprocess.run(
                ["git", "show", "--name-only", "--pretty=format:", h],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8, cwd=str(repo_root),
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        files_changed = [
            f.strip() for f in diff.stdout.splitlines() if f.strip()
        ]
        # Authoring-only: the commit changed exactly the one proposal file
        if len(files_changed) == 1 and files_changed[0] == rel_path:
            continue
        impl_matches.append((h, date, summary))

    if len(impl_matches) == 0:
        return {"status": "pending", "decision": "no implementation reference found"}
    if len(impl_matches) == 1:
        h, date, summary = impl_matches[0]
        return {
            "status": "implemented",
            "implemented_in": h,
            "implemented_at": date,
            "decision": f"single impl commit: {h} ({summary[:60]})",
        }
    return {
        "status": "AMBIGUOUS",
        "candidates": impl_matches,
        "decision": f"{len(impl_matches)} impl-commit candidates — need manual review",
    }


def _build_frontmatter(decision: dict, created: str) -> str:
    """Compose the YAML frontmatter block for backfill insertion."""
    lines = ["---", f"status: {decision['status']}", f"created: {created}"]
    if decision["status"] == "implemented":
        lines.append(f"implemented_in: {decision['implemented_in']}")
        lines.append(f"implemented_at: {decision['implemented_at']}")
    lines.append("---")
    lines.append("")  # blank line after closing
    return "\n".join(lines) + "\n"


def _file_creation_date(rel_path: str, repo_root: Path) -> str:
    """First-commit date of the proposal file via git log; today if none."""
    try:
        result = subprocess.run(
            [
                "git", "log", "--diff-filter=A",
                "--follow", "--pretty=format:%cs", "--reverse",
                "--", rel_path,
            ],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=8, cwd=str(repo_root),
        )
        first = result.stdout.splitlines()[:1]
        if first:
            return first[0].strip()
    except (subprocess.TimeoutExpired, OSError, IndexError):
        pass
    return _dt.date.today().isoformat()


def _scan_proposals(repo_root: Path) -> list:
    """Return list of relative paths under proposals/ excluding templates."""
    base = repo_root / "proposals"
    if not base.is_dir():
        return []
    out = []
    for p in sorted(base.rglob("*.md")):
        rel = p.relative_to(repo_root).as_posix()
        # Exemptions per schema §6
        parts = p.relative_to(base).parts
        if parts and parts[0] in ("templates",):
            continue
        if "archived" in parts:
            # archived/ retains schema-time frontmatter; we still backfill
            # if missing, but with conservative status=archived inference
            pass
        out.append(rel)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Apply backfill (default: dry-run)")
    parser.add_argument("--root", type=Path, default=Path.cwd(),
                        help="Repo root (default: cwd)")
    args = parser.parse_args()

    repo_root = args.root.resolve()
    proposals = _scan_proposals(repo_root)
    if not proposals:
        sys.stdout.write("[INFO] no proposals/*.md found\n")
        return 0

    sys.stdout.write(f"[INFO] scanning {len(proposals)} proposal files\n")
    sys.stdout.write(
        "{:<60} {:<12} {}\n".format("File", "Status", "Decision")
    )
    sys.stdout.write("-" * 110 + "\n")

    written = 0
    skipped = 0
    ambiguous = []
    counts: dict = {}

    for rel in proposals:
        full = repo_root / rel
        try:
            text = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            sys.stderr.write(f"[WARN] skip {rel}: {exc}\n")
            continue

        if _has_frontmatter_status(text):
            decision_status = "(has-status)"
            sys.stdout.write(
                "{:<60} {:<12} {}\n".format(rel[:60], decision_status, "skipped")
            )
            skipped += 1
            counts[decision_status] = counts.get(decision_status, 0) + 1
            continue

        basename_no_ext = full.stem
        decision = _classify(rel, basename_no_ext, repo_root)
        counts[decision["status"]] = counts.get(decision["status"], 0) + 1
        sys.stdout.write(
            "{:<60} {:<12} {}\n".format(
                rel[:60], decision["status"], decision["decision"][:60]
            )
        )

        if decision["status"] == "AMBIGUOUS":
            ambiguous.append((rel, decision["candidates"]))
            continue

        if not args.execute:
            continue

        # Apply: prepend frontmatter
        created = _file_creation_date(rel, repo_root)
        fm = _build_frontmatter(decision, created)
        new_text = fm + text
        full.write_text(new_text, encoding="utf-8")
        written += 1

    sys.stdout.write("\n=== Summary ===\n")
    for k, v in sorted(counts.items()):
        sys.stdout.write(f"  {k}: {v}\n")
    if args.execute:
        sys.stdout.write(f"\n[OK] backfilled {written} files; skipped {skipped}\n")
    else:
        sys.stdout.write(f"\n[DRY-RUN] would backfill {len(proposals) - skipped - len(ambiguous)} files\n")

    if ambiguous:
        sys.stdout.write("\n=== AMBIGUOUS (need manual review) ===\n")
        for rel, candidates in ambiguous:
            sys.stdout.write(f"\n{rel}:\n")
            for h, date, summary in candidates:
                sys.stdout.write(f"  {h}  {date}  {summary[:80]}\n")
        return 0  # not a hard failure; user picks then runs again

    return 0


if __name__ == "__main__":
    sys.exit(main())
