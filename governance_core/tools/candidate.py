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

    candidate.py sweep [--project-root .] [--dry-run] [--repo ...]
        The /wrap-up candidate trigger (P-0072): collect candidate-common
        skills, then uplink every one not already in the dedup ledger.
        The hub project skips; degrades to a report on missing consent /
        network so it never stalls a wrap-up.

    candidate.py review [--project-root .] [--repo ...]
        Hub side: list incoming candidates -- local envelopes under
        candidates/ and open GitHub issues labelled `candidate`.

    candidate.py promote <envelope-dir> [--decision ...] [--note ...]
        Hub side: curate one candidate -- promote its payload into the
        package source (skill / hook kinds), or record a reject / override
        decision. Every decision is written to the consumer registry.

Uplink is consent-gated: .governance/config.json candidate_uplink.consent
must be true (mandatory in the current version, P-0065). A --dry-run preview
sends nothing and is not consent-gated. `review` / `promote` are hub-side
operations -- run by governance-core curating what consumers reported.

Exit codes: 0 ok, 1 blocked / failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from governance_core.candidates import collect as _collect
from governance_core.candidates import envelope as _envelope
from governance_core.candidates import ledger as _ledger
from governance_core.candidates import registry as _registry
from governance_core.candidates import rejected as _rejected
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


def _auth_code(cfg: dict) -> str | None:
    """Return the authorization code from config, or None if absent."""
    if "authorization" in cfg and "auth_code" in cfg["authorization"]:
        return cfg["authorization"]["auth_code"]
    return None


def _consent_ok(cfg: dict) -> bool:
    """Return True if config records candidate-uplink consent."""
    return ("candidate_uplink" in cfg
            and cfg["candidate_uplink"].get("consent") is True)


def _record_uplink(project_root: Path, envelope_dir: Path,
                   issue_url: str) -> None:
    """Record a successful uplink in the dedup ledger (best-effort)."""
    try:
        meta = _envelope.validate_envelope(envelope_dir)
        digest = _ledger.payload_digest(envelope_dir)
        _ledger.record_uplink(_ledger.ledger_path(project_root), digest,
                              meta["id"], issue_url)
    except (_envelope.EnvelopeError, OSError):
        pass  # the ledger is a dedup optimization; never fail uplink on it


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
    auth_code = _auth_code(cfg)
    if auth_code is None:
        sys.stderr.write("[candidate] no authorization code in config "
                         "(run install)\n")
        return 2
    if not args.dry_run and not _consent_ok(cfg):
        sys.stderr.write("[candidate] candidate-uplink consent not recorded "
                         "-- uplink refused\n")
        return 1
    try:
        result = _uplink.uplink_envelope(
            Path(args.envelope_dir), auth_code, repo=args.repo,
            dry_run=args.dry_run)
    except (_uplink.UplinkError, _envelope.EnvelopeError) as exc:
        sys.stderr.write(f"[candidate] uplink failed: {exc}\n")
        return 1
    if not args.dry_run:
        _record_uplink(root, Path(args.envelope_dir), result.strip())
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
    auth_code = _auth_code(cfg)
    if auth_code is None:
        sys.stderr.write("[candidate] no authorization code in config "
                         "(run install)\n")
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
            envelope_dir, auth_code, repo=args.repo, dry_run=args.dry_run)
    except (_uplink.UplinkError, _envelope.EnvelopeError) as exc:
        sys.stderr.write(f"[candidate] submit failed: {exc}\n")
        return 1
    if not args.dry_run:
        _record_uplink(root, envelope_dir, result.strip())
    sys.stdout.write(f"[candidate] envelope: {envelope_dir}\n")
    sys.stdout.write(result + "\n")
    return 0


def cmd_sweep(args: argparse.Namespace) -> int:
    """Collect candidate-common skills and uplink any not yet sent (P-0072).

    The /wrap-up candidate trigger. Runs collect, then uplinks every outbox
    envelope whose payload digest is absent from the dedup ledger. The hub
    project (governance-core itself) has nothing to uplink and skips.
    Degrades to a report -- never blocks -- when consent, network, or `gh`
    is unavailable, so it cannot stall a phase wrap-up.
    """
    root = Path(args.project_root).resolve()
    cfg = _config(root)
    if cfg is None:
        return 2
    origin = _origin(cfg)
    auth_code = _auth_code(cfg)
    if origin is None or auth_code is None:
        sys.stdout.write("[candidate] sweep: project not fully authorized "
                         "-- skipped (no consumer_id / auth code in config)\n")
        return 0
    if origin == "governance-core":
        sys.stdout.write("[candidate] sweep: [N/A -- hub project] "
                         "governance-core curates via review/promote, it "
                         "does not uplink to itself\n")
        return 0

    _collect.collect_netnew_skills(root, origin)
    outbox = _collect.outbox_dir(root)
    envelopes = (sorted({p.parent for p in outbox.rglob("candidate.json")})
                 if outbox.exists() else [])
    led_path = _ledger.ledger_path(root)
    led = _ledger.load_ledger(led_path)

    # P-0076 Phase 1: ledger self-heal. If the consumer-side ledger is
    # empty (lost / wiped / never written) but the outbox has envelopes,
    # try to rebuild ledger entries from the hub's candidate issue history
    # before declaring everything net-new. This avoids re-uplinking the
    # same payloads as fresh candidates just because `_uplinked.json`
    # vanished (the issue that triggered P-0076).
    if envelopes and not led["uplinked"] and shutil.which("gh"):
        recovered = _ledger.discover_uplinked_from_hub(
            origin, repo=args.repo or _uplink.UPSTREAM_REPO)
        for entry in recovered:
            _ledger.record_uplink(led_path, entry["digest"],
                                  entry["candidate_id"], entry["issue_url"])
        if recovered:
            sys.stdout.write(f"[candidate] sweep: ledger self-heal restored "
                             f"{len(recovered)} prior uplink record(s) from "
                             f"the hub\n")
            led = _ledger.load_ledger(led_path)

    # P-0076 Phase 2: consult the shipped rejected_registry.json. If an
    # envelope's payload was previously rejected by the hub, surface the
    # reason+advice so the consumer's owner can stop re-uplinking it.
    rejected_reg = _rejected.load_rejected_registry()

    pending: list[tuple[Path, str]] = []
    blocked: list[tuple[Path, dict]] = []
    name_warnings: list[tuple[Path, dict]] = []
    for env in envelopes:
        try:
            digest = _ledger.payload_digest(env)
            meta = _envelope.validate_envelope(env)
        except _envelope.EnvelopeError:
            continue
        # `title` is the skill name (collect uses `skill.stem`); registry
        # is keyed on full skill_name with `.md` if applicable. Try both
        # to be lenient with how the registry author wrote the entry.
        candidate_names = {meta["title"], meta["title"] + ".md"}
        rej = None
        for n in candidate_names:
            r = _rejected.is_rejected(n, digest, rejected_reg)
            if r is not None:
                rej = r
                break
        if rej is not None and _rejected.should_block(rej):
            blocked.append((env, rej))
            continue
        if rej is not None and rej["match"] == "name":
            # name match without block_by_name -> warn but allow uplink
            name_warnings.append((env, rej))
        if not _ledger.is_uplinked(led, digest):
            pending.append((env, digest))

    for env, rej in blocked:
        advisory = _rejected.format_advisory(
            _envelope.validate_envelope(env)["title"], rej)
        sys.stdout.write("[candidate] sweep: SKIPPED -- " + advisory + "\n")
    for env, rej in name_warnings:
        advisory = _rejected.format_advisory(
            _envelope.validate_envelope(env)["title"], rej)
        sys.stderr.write("[candidate] sweep: NOTE -- " + advisory
                         + "\n  Uplinking the new content for hub "
                         + "re-evaluation.\n")

    if not pending:
        sys.stdout.write("[candidate] sweep: no pending candidates -- "
                         "nothing to uplink\n")
        return 0
    if not args.dry_run and not _consent_ok(cfg):
        sys.stdout.write(f"[candidate] sweep: {len(pending)} pending "
                         f"candidate(s), but candidate-uplink consent is not "
                         f"recorded -- not uplinked (re-run install to "
                         f"consent)\n")
        return 0

    sent = 0
    for env, digest in pending:
        try:
            meta = _envelope.validate_envelope(env)
            result = _uplink.uplink_envelope(env, auth_code, repo=args.repo,
                                             dry_run=args.dry_run)
        except (_uplink.UplinkError, _envelope.EnvelopeError) as exc:
            sys.stderr.write(f"[candidate] sweep: skipped {env.name} -- "
                             f"{exc}\n")
            continue
        if args.dry_run:
            sys.stdout.write(f"[candidate] sweep: would uplink {meta['id']}\n")
        else:
            _ledger.record_uplink(led_path, digest, meta["id"],
                                  result.strip())
            sys.stdout.write(f"[candidate] sweep: uplinked {meta['id']} -> "
                             f"{result.strip()}\n")
            sent += 1
    if args.dry_run:
        sys.stdout.write(f"[candidate] sweep dry-run: {len(pending)} pending "
                         f"candidate(s) would be uplinked\n")
    else:
        sys.stdout.write(f"[candidate] sweep: uplinked {sent}/{len(pending)} "
                         f"pending candidate(s)\n")
    return 0


def _incoming_dir(project_root: Path) -> Path:
    """Return the hub-side incoming candidates directory."""
    return project_root / "candidates"


def _registry_path(project_root: Path) -> Path:
    """Return the consumer registry path (maintainer-side, committed)."""
    return project_root / "maintainer" / "consumer_registry.json"


def cmd_review(args: argparse.Namespace) -> int:
    """List incoming candidates: local envelopes + labeled GitHub issues."""
    root = Path(args.project_root).resolve()
    incoming = _incoming_dir(root)
    reg = _registry.load_registry(_registry_path(root))
    decided = {c["id"]: c["decision"] for c in reg["candidates"]}

    local = sorted(incoming.rglob("candidate.json")) if incoming.exists() else []
    sys.stdout.write(f"=== local incoming envelopes ({len(local)}) ===\n")
    for meta_file in local:
        env_dir = meta_file.parent
        try:
            meta = _envelope.validate_envelope(env_dir)
        except _envelope.EnvelopeError as exc:
            sys.stdout.write(f"  {env_dir}  INVALID: {exc}\n")
            continue
        status = decided[meta["id"]] if meta["id"] in decided else "pending"
        flag = ("  [REVOKED ORIGIN]" if _registry.is_consumer_revoked(
            _registry_path(root), meta["origin"]) else "")
        sys.stdout.write(f"  {meta['id']}  kind={meta['kind']} "
                         f"origin={meta['origin']}  [{status}]{flag}  "
                         f"{env_dir}\n")

    sys.stdout.write("=== open GitHub candidate issues ===\n")
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--repo", args.repo, "--label",
             "candidate", "--state", "open", "--json", "number,title,url"],
            capture_output=True, text=True, check=True)
        issues = json.loads(result.stdout)
        if not issues:
            sys.stdout.write("  (none open)\n")
        for issue in issues:
            sys.stdout.write(f"  #{issue['number']}  {issue['title']}\n"
                             f"    {issue['url']}\n")
    except FileNotFoundError:
        sys.stdout.write("  (gh CLI not available -- skipped)\n")
    except subprocess.CalledProcessError as exc:
        sys.stdout.write(f"  (gh issue list failed: {exc.stderr.strip()})\n")
    return 0


def cmd_promote(args: argparse.Namespace) -> int:
    """Curate one candidate: promote into the package source, or reject."""
    root = Path(args.project_root).resolve()
    try:
        meta = _envelope.validate_envelope(Path(args.envelope_dir))
    except _envelope.EnvelopeError as exc:
        sys.stderr.write(f"[candidate] invalid envelope: {exc}\n")
        return 1
    env_dir = Path(args.envelope_dir)

    # P-0071 Phase 4: a candidate from a revoked origin is hard-rejected --
    # GC no longer carries that owner's common-layer role, so its
    # contributions are not folded in regardless of the requested decision.
    if _registry.is_consumer_revoked(_registry_path(root), meta["origin"]):
        sys.stderr.write(f"[candidate] origin {meta['origin']!r} is a "
                         f"REVOKED consumer -- promotion refused\n")
        _registry.record_candidate(
            _registry_path(root), meta["id"], meta["origin"], meta["kind"],
            meta["title"], "rejected",
            note=f"auto-rejected: origin {meta['origin']} is revoked")
        sys.stdout.write(f"[candidate] recorded rejection for {meta['id']} "
                         f"(revoked origin)\n")
        return 1

    if args.decision == "promoted":
        pkg = root / "governance_core"
        dest_of = {"skill": pkg / "skills", "hook": pkg / "hooks"}
        if meta["kind"] in dest_of:
            dest = dest_of[meta["kind"]]
            dest.mkdir(parents=True, exist_ok=True)
            for rel in meta["source_paths"]:
                src = env_dir / rel
                shutil.copy2(src, dest / src.name)
                sys.stdout.write(f"[candidate] promoted {src.name} -> "
                                 f"{dest.relative_to(root).as_posix()}\n")
        else:  # mechanism: multi-file, needs human placement judgment
            sys.stdout.write("[candidate] kind=mechanism -- place these "
                             "payload files into the package source by "
                             "hand:\n")
            for rel in meta["source_paths"]:
                sys.stdout.write(f"  {env_dir / rel}\n")

    _registry.record_candidate(_registry_path(root), meta["id"],
                               meta["origin"], meta["kind"], meta["title"],
                               args.decision, note=args.note)
    sys.stdout.write(f"[candidate] recorded decision '{args.decision}' for "
                     f"{meta['id']}\n")
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

    p_sweep = sub.add_parser("sweep")
    p_sweep.add_argument("--project-root", default=".")
    p_sweep.add_argument("--repo", default=_uplink.UPSTREAM_REPO)
    p_sweep.add_argument("--dry-run", action="store_true")
    p_sweep.set_defaults(func=cmd_sweep)

    p_review = sub.add_parser("review")
    p_review.add_argument("--project-root", default=".")
    p_review.add_argument("--repo", default=_uplink.UPSTREAM_REPO)
    p_review.set_defaults(func=cmd_review)

    p_promote = sub.add_parser("promote")
    p_promote.add_argument("envelope_dir")
    p_promote.add_argument("--decision", default="promoted",
                           choices=["promoted", "rejected", "override"])
    p_promote.add_argument("--note", default="")
    p_promote.add_argument("--project-root", default=".")
    p_promote.set_defaults(func=cmd_promote)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
