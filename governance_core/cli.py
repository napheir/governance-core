"""governance-core CLI.

Subcommands:

    governance-core install --auth-code CODE [--accept-candidate-uplink]
                            [--project-root PATH] [--config-overrides JSON]
        Set up .governance/ in the downstream project: write config.json,
        copy hooks/skills/commands/agents/contracts/agent_rules from this
        package to .claude/<category>/, render clauses to .governance/clauses/.
        Requires a maintainer-issued authorization code and candidate-uplink
        consent (P-0065); the governance layer is materialized only after
        both gates pass. Idempotent: re-running refreshes content without
        touching business files at the project root.

    governance-core upgrade [--auth-code CODE] [--project-root PATH]
        Same as install but only refreshes governance assets; preserves
        existing .governance/config.json. Re-verifies the stored
        authorization code (or --auth-code if given).

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
        auth_code=args.auth_code,
        accept_candidate_uplink=args.accept_candidate_uplink,
    )


def cmd_upgrade(args: argparse.Namespace) -> int:
    from governance_core.installer import install
    return install(
        project_root=Path(args.project_root).resolve(),
        config_overrides={},  # preserve existing config
        preserve_config=True,
        force=True,
        auth_code=args.auth_code,
        accept_candidate_uplink=args.accept_candidate_uplink,
        prune=not args.no_prune,
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
    p_install.add_argument("--auth-code", default=None,
                           help="maintainer-issued authorization code (required)")
    p_install.add_argument("--accept-candidate-uplink", action="store_true",
                           help="consent to candidate uplink (required this version)")
    p_install.set_defaults(func=cmd_install)

    p_upgrade = sub.add_parser("upgrade")
    p_upgrade.add_argument("--project-root", default=".")
    p_upgrade.add_argument("--auth-code", default=None,
                           help="authorization code (defaults to the stored one)")
    p_upgrade.add_argument("--accept-candidate-uplink", action="store_true",
                           help="consent to candidate uplink if not already recorded")
    p_upgrade.add_argument("--no-prune", action="store_true",
                           help="keep autonomy-layer files dropped from the package source")
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
