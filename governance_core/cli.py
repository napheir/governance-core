"""governance-core CLI.

Subcommands:

    governance-core install [--project-root PATH] [--config-overrides JSON]
        Set up .governance/ in the downstream project: write config.json,
        copy hooks/skills/commands/agents/contracts/agent_rules from this
        package to .claude/<category>/, render clauses to .governance/clauses/.
        Idempotent: re-running refreshes content without touching business
        files at the project root.

    governance-core upgrade [--project-root PATH]
        Same as install but only refreshes governance assets; preserves
        existing .governance/config.json.

    governance-core doctor [--project-root PATH]
        Validate downstream project's governance configuration:
        - .governance/config.json schema validity
        - All required hooks installed
        - Skills/commands discoverable

    governance-core render-clauses [--out PATH]
        Render generic clauses to PATH with current config substitutions.

    governance-core version
        Print package version.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_install(args: argparse.Namespace) -> int:
    from governance_core.installer import install
    return install(
        project_root=Path(args.project_root).resolve(),
        config_overrides=json.loads(args.config_overrides) if args.config_overrides else {},
        force=args.force,
    )


def cmd_upgrade(args: argparse.Namespace) -> int:
    from governance_core.installer import install
    return install(
        project_root=Path(args.project_root).resolve(),
        config_overrides={},  # preserve existing config
        preserve_config=True,
        force=True,
    )


def cmd_doctor(args: argparse.Namespace) -> int:
    from governance_core.installer import doctor
    return doctor(project_root=Path(args.project_root).resolve())


def cmd_render_clauses(args: argparse.Namespace) -> int:
    from governance_core.installer import render_clauses
    return render_clauses(out_dir=Path(args.out).resolve(), project_root=Path(args.project_root).resolve())


def cmd_version(args: argparse.Namespace) -> int:
    from governance_core import __version__
    print(f"governance-core {__version__}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="governance-core")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_install = sub.add_parser("install")
    p_install.add_argument("--project-root", default=".")
    p_install.add_argument("--config-overrides", default="", help="JSON dict to merge into config.json")
    p_install.add_argument("--force", action="store_true")
    p_install.set_defaults(func=cmd_install)

    p_upgrade = sub.add_parser("upgrade")
    p_upgrade.add_argument("--project-root", default=".")
    p_upgrade.set_defaults(func=cmd_upgrade)

    p_doctor = sub.add_parser("doctor")
    p_doctor.add_argument("--project-root", default=".")
    p_doctor.set_defaults(func=cmd_doctor)

    p_render = sub.add_parser("render-clauses")
    p_render.add_argument("--out", required=True)
    p_render.add_argument("--project-root", default=".")
    p_render.set_defaults(func=cmd_render_clauses)

    p_version = sub.add_parser("version")
    p_version.set_defaults(func=cmd_version)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
