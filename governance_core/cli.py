"""governance-core CLI entry point.

Subcommands (to be implemented in Phase 1.2+):

    governance-core install [--project-root PATH]
        Render clauses to <project>/.governance/clauses/, symlink/copy hooks
        and skills to <project>/.claude/, register .gitattributes per-branch
        merge=ours driver, run git config for each clone.

    governance-core upgrade [--project-root PATH]
        Re-render clauses + refresh hooks/skills from current installed
        governance-core version; business resources untouched.

    governance-core doctor [--project-root PATH]
        Verify downstream project's .governance/config.json schema validity,
        cross-clone venv consistency, hook installation completeness.

    governance-core render-clauses [--out PATH]
        Standalone clause rendering (used by template's bootstrap script).
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(prog="governance-core")
    parser.add_argument(
        "subcommand",
        choices=["install", "upgrade", "doctor", "render-clauses", "version"],
    )
    parser.add_argument("--project-root", default=".")
    args, rest = parser.parse_known_args()

    if args.subcommand == "version":
        from governance_core import __version__
        print(f"governance-core {__version__}")
        return 0

    print(
        f"[governance-core] subcommand={args.subcommand!r} project_root={args.project_root!r}",
        file=sys.stderr,
    )
    print("  Not yet implemented (P-0059 Phase 1.2+).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
