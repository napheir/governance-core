"""Query whether a path is governance-core install-managed or business.

Reads `.governance/installed_files.json` -- the P-0065 Phase 2 manifest that
`governance-core install` / `upgrade` writes. A path listed there is
install-managed: the installer owns it and `upgrade` overwrites local edits.
A path absent from the manifest is business -- project-owned, never touched
by the installer.

Usage:
    python tools/whichlayer.py <path> [--project-root .]

Exit codes:
    0 = install-managed   1 = business   2 = error (no manifest / bad path)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    """Classify one path against the installed-files manifest."""
    parser = argparse.ArgumentParser(prog="whichlayer")
    parser.add_argument("path", help="file path to classify")
    parser.add_argument("--project-root", default=".",
                        help="consuming project root (default: .)")
    args = parser.parse_args()

    root = Path(args.project_root).resolve()
    manifest_path = root / ".governance" / "installed_files.json"
    if not manifest_path.exists():
        sys.stderr.write(
            f"[whichlayer] no manifest at {manifest_path} "
            "-- run governance-core install/upgrade first\n"
        )
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    managed = {entry["path"]: entry["category"] for entry in manifest["files"]}

    # Normalize the queried path to project-root-relative POSIX form.
    target = Path(args.path)
    if target.is_absolute():
        try:
            rel = target.resolve().relative_to(root).as_posix()
        except ValueError:
            sys.stderr.write(
                f"[whichlayer] path is outside project root: {target}\n")
            return 2
    else:
        rel = target.as_posix()

    if rel in managed:
        sys.stdout.write(f"install-managed\t{managed[rel]}\t{rel}\n")
        return 0
    sys.stdout.write(f"business\t-\t{rel}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
