"""governance-core candidate pipeline CLI (P-0065 Phase 4).

Subcommands:

    candidate.py collect [--project-root .]
        Scan .claude/skills/learned/ for layer: candidate-common skills and
        package each as a candidate envelope in the outbox.

    candidate.py submit --kind {skill,hook,mechanism} --title T
        --rationale R --files a,b,c [--layer ...] [--dry-run] [--repo ...]
        Build a candidate envelope from loose files and uplink it.

    candidate.py uplink <envelope-dir> [--dry-run] [--repo ...]
        Scan and uplink an existing candidate envelope -- e.g. one produced
        by `collect` or captured as installer drift.

Uplink is consent-gated: .governance/config.json candidate_uplink.consent
must be true (mandatory in the current version, P-0065). A --dry-run preview
sends nothing and is not consent-gated.

Exit codes: 0 ok, 1 blocked / failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from governance_core.candidates import collect as _collect
from governance_core.candidates import envelope as _envelope
from governance_core.candidates import uplink as _uplink


def _config(project_root: Path) -> dict | None:
    """Load .governance/config.json, or None (with a message) if absent."""
    cfg_path = project_root / ".governance" / "config.json"
    if not cfg_path.exists():
        sys.stderr.write(f"[candidate] no .governance/config.json at "
                         f"{project_root}\n")
        return None
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def _origin(cfg: dict) -> str | None:
    """Return the consumer_id from config, or None if unauthorized."""
    if "authorization" in cfg and "consumer_id" in cfg["authorization"]:
        return cfg["authorization"]["consumer_id"]
    return None


def _consent_ok(cfg: dict) -> bool:
    """Return True if config records candidate-uplink consent."""
    return ("candidate_uplink" in cfg
            and cfg["candidate_uplink"].get("consent") is True)


def cmd_collect(args: argparse.Namespace) -> int:
    """Collect net-new candidate-common learned skills into the outbox."""
    root = Path(args.project_root).resolve()
    cfg = _config(root)
    if cfg is None:
        return 2
    origin = _origin(cfg)
    if origin is None:
        sys.stderr.write("[candidate] no consumer_id in config (run install)\n")
        return 2
    built = _collect.collect_netnew_skills(root, origin)
    if not built:
        sys.stdout.write("[candidate] collect: no candidate-common learned "
                         "skills found\n")
        return 0
    for envelope_dir in built:
        sys.stdout.write(f"[candidate] collected -> {envelope_dir}\n")
    sys.stdout.write(f"[candidate] {len(built)} envelope(s) staged in the "
                     f"outbox\n")
    return 0


def cmd_uplink(args: argparse.Namespace) -> int:
    """Scan and uplink an existing candidate envelope."""
    root = Path(args.project_root).resolve()
    cfg = _config(root)
    if cfg is None:
        return 2
    if not args.dry_run and not _consent_ok(cfg):
        sys.stderr.write("[candidate] candidate-uplink consent not recorded "
                         "-- uplink refused\n")
        return 1
    try:
        result = _uplink.uplink_envelope(
            Path(args.envelope_dir), repo=args.repo, dry_run=args.dry_run)
    except (_uplink.UplinkError, _envelope.EnvelopeError) as exc:
        sys.stderr.write(f"[candidate] uplink failed: {exc}\n")
        return 1
    sys.stdout.write(result + "\n")
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    """Build a candidate envelope from loose files, then uplink it."""
    root = Path(args.project_root).resolve()
    cfg = _config(root)
    if cfg is None:
        return 2
    origin = _origin(cfg)
    if origin is None:
        sys.stderr.write("[candidate] no consumer_id in config (run install)\n")
        return 2
    if not args.dry_run and not _consent_ok(cfg):
        sys.stderr.write("[candidate] candidate-uplink consent not recorded "
                         "-- submit refused\n")
        return 1
    files = [Path(p.strip()) for p in args.files.split(",") if p.strip()]
    missing = [str(f) for f in files if not f.exists()]
    if missing:
        sys.stderr.write(f"[candidate] file(s) not found: {missing}\n")
        return 2
    try:
        envelope_dir = _envelope.build_envelope(
            _collect.outbox_dir(root), kind=args.kind, origin=origin,
            title=args.title, rationale=args.rationale,
            payload_files=files, layer=args.layer)
        result = _uplink.uplink_envelope(
            envelope_dir, repo=args.repo, dry_run=args.dry_run)
    except (_uplink.UplinkError, _envelope.EnvelopeError) as exc:
        sys.stderr.write(f"[candidate] submit failed: {exc}\n")
        return 1
    sys.stdout.write(f"[candidate] envelope: {envelope_dir}\n")
    sys.stdout.write(result + "\n")
    return 0


def main() -> int:
    """Dispatch a candidate-pipeline subcommand."""
    parser = argparse.ArgumentParser(prog="candidate")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_collect = sub.add_parser("collect")
    p_collect.add_argument("--project-root", default=".")
    p_collect.set_defaults(func=cmd_collect)

    p_uplink = sub.add_parser("uplink")
    p_uplink.add_argument("envelope_dir")
    p_uplink.add_argument("--project-root", default=".")
    p_uplink.add_argument("--repo", default=_uplink.UPSTREAM_REPO)
    p_uplink.add_argument("--dry-run", action="store_true")
    p_uplink.set_defaults(func=cmd_uplink)

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--kind", required=True,
                          choices=["skill", "hook", "mechanism"])
    p_submit.add_argument("--title", required=True)
    p_submit.add_argument("--rationale", required=True)
    p_submit.add_argument("--files", required=True,
                          help="comma-separated payload file paths")
    p_submit.add_argument("--layer", default="candidate-common",
                          choices=["candidate-common", "business"])
    p_submit.add_argument("--project-root", default=".")
    p_submit.add_argument("--repo", default=_uplink.UPSTREAM_REPO)
    p_submit.add_argument("--dry-run", action="store_true")
    p_submit.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
