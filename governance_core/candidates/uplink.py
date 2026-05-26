"""Candidate uplink: secret scan + GitHub-issue transport (P-0065 Phase 4).

A candidate envelope reaches governance-core as a GitHub issue (the form
locked in P-0065 Phase 0): the consumer needs only a GitHub account and the
`gh` CLI -- no fork, no write access. Before transport the payload is
scanned for secrets at HIGH+MEDIUM severity (the destination is a public
repo); any hit aborts the uplink.

The envelope travels inline in the issue body. Governance candidates are
kilobyte-scale, so a body-size guard refuses the rare oversized envelope
rather than silently truncating it.

Attribution (P-0071 Phase 4): an uplink also verifies the candidate's
`origin` against the project's authorization code. The code is signed, so
its `consumer_id` is authentic; binding `origin` to it means a candidate
cannot be uplinked under a forged origin.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from governance_core.auth import codec
from governance_core.candidates import envelope
from governance_core import sensitive_scan

UPSTREAM_REPO = "napheir/governance-core"
ISSUE_BODY_LIMIT = 60000
CANDIDATE_LABEL = "candidate"


class UplinkError(Exception):
    """Raised when a candidate cannot be uplinked (secret, oversize, gh)."""


def _authorized_consumer(auth_code: str) -> str:
    """Verify `auth_code`; return its consumer_id. Raises UplinkError if bad."""
    try:
        payload = codec.verify_auth_code(
            auth_code, codec.load_bundled_public_key())
    except codec.AuthCodeError as exc:
        raise UplinkError(
            f"authorization code does not verify -- cannot uplink: {exc}")
    return payload["consumer_id"]


def scan_envelope(envelope_dir: Path) -> list[sensitive_scan.Finding]:
    """Scan every payload file of an envelope for secrets (HIGH + MEDIUM)."""
    meta = envelope.validate_envelope(envelope_dir)
    findings: list[sensitive_scan.Finding] = []
    for rel in meta["source_paths"]:
        findings.extend(sensitive_scan.scan_file(
            envelope_dir / rel, min_severity=sensitive_scan.MEDIUM))
    return findings


def build_issue(envelope_dir: Path) -> tuple[str, str, list[str]]:
    """Build the (title, body, labels) for a candidate envelope's issue.

    Raises UplinkError if the assembled body exceeds the issue size guard.
    """
    meta = envelope.validate_envelope(envelope_dir)
    title = (f"[candidate] {meta['kind']}: {meta['title']} "
             f"(from {meta['origin']})")
    labels = [CANDIDATE_LABEL, f"kind/{meta['kind']}"]

    parts = [
        f"## Candidate: {meta['title']}",
        "",
        f"- id: `{meta['id']}`",
        f"- kind: `{meta['kind']}`",
        f"- origin: `{meta['origin']}`",
        f"- layer: `{meta['layer']}`",
        f"- created: {meta['created']}",
    ]
    if "drift_target" in meta:
        parts.append(f"- drift_target: `{meta['drift_target']}`")
        parts.append(f"- baseline_sha256: `{meta['baseline_sha256']}`")
    parts += ["", "### Rationale", "", meta["rationale"], "",
              "### candidate.json", "```json",
              (envelope_dir / envelope.CANDIDATE_JSON).read_text(
                  encoding="utf-8").rstrip(), "```"]
    for rel in meta["source_paths"]:
        # P-0076 Phase 1: do NOT rstrip the payload. `ledger.payload_digest`
        # hashes the raw file bytes, so issue body must carry them verbatim
        # for `discover_uplinked_from_hub` to rebuild a matching digest.
        # Trailing newlines are preserved; the fenced block closes cleanly
        # either way (the trailing ``` sits on its own line below).
        parts += ["", f"### {rel}", "```",
                  (envelope_dir / rel).read_text(encoding="utf-8"),
                  "```"]
    body = "\n".join(parts) + "\n"
    if len(body) > ISSUE_BODY_LIMIT:
        raise UplinkError(
            f"candidate envelope too large for issue uplink "
            f"({len(body)} > {ISSUE_BODY_LIMIT} chars) -- contact the "
            f"governance-core maintainer for an alternate channel")
    return title, body, labels


def gh_command(title: str, body: str, labels: list[str],
               repo: str) -> list[str]:
    """Build the `gh issue create` argv for a candidate issue."""
    argv = ["gh", "issue", "create", "--repo", repo,
            "--title", title, "--body", body]
    for label in labels:
        argv += ["--label", label]
    return argv


def uplink_envelope(envelope_dir: Path, auth_code: str,
                    repo: str = UPSTREAM_REPO, dry_run: bool = False) -> str:
    """Scan, then uplink a candidate envelope as a GitHub issue.

    `auth_code` is the project's authorization code: the envelope's `origin`
    must equal the verified code's consumer_id, or the uplink aborts -- a
    candidate cannot be uplinked under a forged origin. Also aborts
    (UplinkError) if the payload carries a secret or is oversized.

    With `dry_run`, returns the would-run gh argv as text without executing.
    Otherwise runs `gh issue create` and returns the created issue URL.
    """
    meta = envelope.validate_envelope(envelope_dir)
    consumer_id = _authorized_consumer(auth_code)
    if meta["origin"] != consumer_id:
        raise UplinkError(
            f"candidate origin {meta['origin']!r} does not match the "
            f"authorized consumer_id {consumer_id!r} -- origin is bound to "
            f"the signed auth code and cannot be forged")

    findings = scan_envelope(envelope_dir)
    if findings:
        lines = "\n".join(f"  - {f.pattern} (severity {f.severity}, "
                          f"line {f.line}): {f.excerpt}" for f in findings)
        raise UplinkError(
            f"candidate payload carries {len(findings)} potential "
            f"secret(s) -- uplink to a PUBLIC repo aborted:\n{lines}")

    title, body, labels = build_issue(envelope_dir)
    argv = gh_command(title, body, labels, repo)
    if dry_run:
        shown = argv[:-1] + [f"<body {len(body)} chars>"]
        return ("[dry-run] would run:\n  " + " ".join(shown)
                + f"\n\n--- issue title ---\n{title}\n"
                + f"--- issue body ---\n{body}")
    try:
        result = subprocess.run(argv, capture_output=True, text=True,
                                check=True)
    except FileNotFoundError:
        raise UplinkError("`gh` CLI not found -- install GitHub CLI to uplink")
    except subprocess.CalledProcessError as exc:
        raise UplinkError(f"gh issue create failed: {exc.stderr.strip()}")
    return result.stdout.strip()
