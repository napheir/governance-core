"""Classify per-file git diff status for federated knowledge collection.

Used by `/publish-knowledge` Step 4.2 (P-0055) to decide whether a Modified
file in a non-core feature branch is safe to pull to master.

Classification:
- A           : Added (new file in head)            -> safe to collect
- M-fm-only   : Modified, but diff entirely within YAML frontmatter region
                (lines 1..fm_close on both sides), no body lines touched
                -> safe to collect (e.g., adding `briefing:` per v1.1.0
                schema, bumping `updated:` date)
- M-mixed     : Modified, with at least one + or - line outside the
                frontmatter region                  -> skip + WARN
- D           : Deleted in head                     -> skip silently
- ?           : Any other status (R/C/T/U)          -> skip + WARN
                (we do not auto-collect renames; owner should handle)

Frontmatter boundary rule (hard, contract-aligned):
  - File line 1 MUST be `---` (after optional BOM stripped) to be
    considered a frontmatter document.
  - The first standalone `---` at line >= 2 closes the frontmatter.
  - Body `---` separators (after the close) do not affect classification.
  - If either side lacks a recognizable frontmatter envelope, the file
    is classified M-mixed (conservative — fail-closed).

This module is consumed by `tools/publish_knowledge_collect.py` / the
`/publish-knowledge` skill text. It is per-clone safe (no global state).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a git command rooted at repo_root. Return CompletedProcess.

    Caller decides whether to raise; we do not auto-check so the caller
    can classify failures as M-mixed (conservative).
    """
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _find_fm_close(content: str) -> int | None:
    """Return 1-based line number of the closing `---` for YAML frontmatter.

    Returns None when the file does not start with `---` or the closer is
    absent. Strips a leading UTF-8 BOM if present.
    """
    if content.startswith("﻿"):
        content = content[1:]
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for idx, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return idx
    return None


def _parse_hunks(diff_text: str) -> tuple[list[int], list[int]]:
    """Parse `git diff --unified=0` output into (added_new_lines, removed_old_lines).

    Each list contains 1-based line numbers — added in the new file, removed
    in the old file.
    """
    added: list[int] = []
    removed: list[int] = []
    new_lineno: int | None = None
    old_lineno: int | None = None
    for raw in diff_text.splitlines():
        m = _HUNK_RE.match(raw)
        if m:
            old_lineno = int(m.group(1))
            new_lineno = int(m.group(3))
            continue
        if new_lineno is None or old_lineno is None:
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if raw.startswith("+"):
            added.append(new_lineno)
            new_lineno += 1
        elif raw.startswith("-"):
            removed.append(old_lineno)
            old_lineno += 1
        elif raw.startswith(" "):
            # Should not appear with --unified=0, but stay defensive.
            new_lineno += 1
            old_lineno += 1


    return added, removed


def _name_status(
    repo_root: Path, base_ref: str, head_ref: str, paths: Iterable[str]
) -> list[tuple[str, str]]:
    """Return [(status_char, path), ...] for the diff between base and head.

    status_char is the first character of the git diff status (A/M/D/R/...)
    which is what /publish-knowledge currently inspects.
    """
    res = _git(
        repo_root,
        "diff",
        "--name-status",
        base_ref,
        head_ref,
        "--",
        *paths,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"git diff --name-status failed (rc={res.returncode}): {res.stderr.strip()}"
        )
    rows: list[tuple[str, str]] = []
    for line in res.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append((parts[0][:1], parts[-1]))
    return rows


def _fm_direction(added_in_fm: int, removed_in_fm: int) -> str:
    """Direction of a frontmatter-region diff, base=hub vs head=clone.

    - ``ahead``  : clone has fm line(s) the hub lacks (added_in_fm > 0, no
      removals) -> genuinely net-new -> collect.
    - ``behind`` : clone merely lags the hub (added_in_fm == 0, removed_in_fm
      > 0; the "removed" line is a field the hub just added) -> skip; the clone
      catches up when it merges the hub (issue #132).
    - ``mixed``  : both added and removed fm lines -> carries net-new fm content
      the hub lacks -> collect (the removed line is caught up on merge).
    - ``na``     : no fm-region change counted.
    """
    if added_in_fm > 0 and removed_in_fm > 0:
        return "mixed"
    if added_in_fm > 0:
        return "ahead"
    if removed_in_fm > 0:
        return "behind"
    return "na"


def classify_knowledge_diff(
    repo_root: Path,
    base_ref: str,
    head_ref: str,
    paths: Iterable[str],
) -> list[dict]:
    """Classify every changed file between two refs under the given paths.

    Returns a list of dicts:
      {
        "path": str,
        "status": "A" | "M-fm-only" | "M-mixed" | "D" | "?",
        "reason": str,
        "added_in_fm": int,         # M-* only: count of + lines inside fm
        "removed_in_fm": int,       # M-* only: count of - lines inside fm
        "first_violation_line": int,# M-mixed only: 1-based line in new file
        "direction": str            # frontmatter diff direction; see _fm_direction
      }

    `direction` is meaningful only when base_ref is the hub and head_ref is the
    clone (as /publish-knowledge Step 4 invokes it: --base HEAD --head
    FETCH_HEAD). It lets Step 4 skip `behind` files (a clone merely lagging the
    hub) so a collect never reverts a hub-authored frontmatter field (issue
    #132). Records without frontmatter counts (A / D / ? / undetectable-fm
    M-mixed) get "na".
    """
    paths = list(paths)
    results: list[dict] = []
    for status_char, path in _name_status(repo_root, base_ref, head_ref, paths):
        if status_char == "A":
            results.append({"path": path, "status": "A", "reason": "newly added"})
            continue
        if status_char == "D":
            results.append({"path": path, "status": "D", "reason": "deleted in head"})
            continue
        if status_char != "M":
            results.append(
                {
                    "path": path,
                    "status": "?",
                    "reason": f"unsupported git status {status_char!r} (rename/copy/unmerged not auto-collected)",
                }
            )
            continue

        diff_res = _git(
            repo_root,
            "diff",
            "--unified=0",
            base_ref,
            head_ref,
            "--",
            path,
        )
        if diff_res.returncode != 0:
            results.append(
                {
                    "path": path,
                    "status": "M-mixed",
                    "reason": f"git diff failed (rc={diff_res.returncode}); fail-closed",
                }
            )
            continue

        added_lines, removed_lines = _parse_hunks(diff_res.stdout)

        new_content_res = _git(repo_root, "show", f"{head_ref}:{path}")
        old_content_res = _git(repo_root, "show", f"{base_ref}:{path}")
        new_fm = _find_fm_close(new_content_res.stdout) if new_content_res.returncode == 0 else None
        old_fm = _find_fm_close(old_content_res.stdout) if old_content_res.returncode == 0 else None

        if new_fm is None or old_fm is None:
            results.append(
                {
                    "path": path,
                    "status": "M-mixed",
                    "reason": (
                        f"no frontmatter envelope detected "
                        f"(new_fm_close={new_fm}, old_fm_close={old_fm})"
                    ),
                }
            )
            continue

        out_added = [n for n in added_lines if n > new_fm]
        out_removed = [n for n in removed_lines if n > old_fm]

        if out_added or out_removed:
            first_violation = (out_added + out_removed)[0]
            results.append(
                {
                    "path": path,
                    "status": "M-mixed",
                    "reason": f"body change detected at line {first_violation}",
                    "first_violation_line": first_violation,
                    "added_in_fm": len(added_lines) - len(out_added),
                    "removed_in_fm": len(removed_lines) - len(out_removed),
                }
            )
        else:
            results.append(
                {
                    "path": path,
                    "status": "M-fm-only",
                    "reason": (
                        f"frontmatter-only change "
                        f"({len(added_lines)} added / {len(removed_lines)} removed inside fm region)"
                    ),
                    "added_in_fm": len(added_lines),
                    "removed_in_fm": len(removed_lines),
                }
            )

    # Derive `direction` uniformly: records carrying fm counts (M-fm-only and
    # M-mixed-with-counts) get ahead|behind|mixed; all others (A / D / ? /
    # undetectable-fm M-mixed) get "na". Single point so every record has the
    # key (issue #132: Step 4 gates M-fm-only collection on direction != behind).
    for record in results:
        if "added_in_fm" in record and "removed_in_fm" in record:
            record["direction"] = _fm_direction(
                record["added_in_fm"], record["removed_in_fm"]
            )
        else:
            record["direction"] = "na"
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Classify knowledge/** file diffs as A | M-fm-only | M-mixed | D | ? for /publish-knowledge"
    )
    p.add_argument("--base", required=True, help="Base git ref (e.g. HEAD, origin/master)")
    p.add_argument("--head", required=True, help="Head git ref (e.g. FETCH_HEAD)")
    p.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="Path scope passed to git diff -- (e.g. knowledge/)",
    )
    p.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    args = p.parse_args(argv)

    try:
        results = classify_knowledge_diff(
            Path(args.repo_root).resolve(), args.base, args.head, args.paths
        )
    except RuntimeError as e:
        print(f"[ERR] {e}", file=sys.stderr)
        return 2

    for r in results:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
