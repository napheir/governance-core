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

import difflib
import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("governance_core.candidates.uplink")

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


def _baseline_for_drift(meta: dict) -> Path | None:
    """Locate the upstream baseline file for a drift envelope's `drift_target`.

    Returns the package-source path under `governance_core/` corresponding
    to the drift target's autonomy-layer path, or None when the path is
    not install-managed (or the package source is missing). P-0077 uses
    this to render a unified diff against baseline instead of shipping
    the entire current file.
    """
    if "drift_target" not in meta:
        return None
    # Local import to avoid the candidates module importing installer at
    # package init time -- installer is a heavier module and pulls in
    # subprocess + git plumbing transitively.
    from governance_core.installer import _pkg_source_path
    src = _pkg_source_path(meta["drift_target"])
    if src is None or not src.exists():
        return None
    return src


def build_issue(envelope_dir: Path) -> tuple[str, str, list[str]]:
    """Build the (title, body, labels) for a candidate envelope's issue.

    For a drift envelope (P-0077): the body carries a unified diff
    against the upstream baseline plus a `payload_form: diff` /
    `payload_sha256:` metadata pair, instead of the full current file.
    The hub already ships the baseline bytes; no need to retransmit
    them. Falls back to the legacy full-payload form when the baseline
    cannot be located (unfamiliar drift_target, missing package
    source) so uplink never blocks on a baseline-lookup failure.

    Net-new envelopes (no `drift_target`) still ship the full payload
    fence -- P-0076 Phase 1's `discover_uplinked_from_hub` rebuilds the
    digest by rehashing those fenced bytes.

    Raises UplinkError if the assembled body exceeds the issue size guard.
    """
    meta = envelope.validate_envelope(envelope_dir)
    title = (f"[candidate] {meta['kind']}: {meta['title']} "
             f"(from {meta['origin']})")
    labels = [CANDIDATE_LABEL, f"kind/{meta['kind']}"]

    baseline = _baseline_for_drift(meta)
    drift_form = baseline is not None  # only "diff" when we can actually diff

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
    if drift_form:
        # Compute consumer's payload sha256 so the hub-side parser can
        # take it directly without rehashing the diff (which would not
        # reconstruct the original bytes).
        payload_rel = meta["source_paths"][0]
        current_bytes = (envelope_dir / payload_rel).read_bytes()
        payload_sha = hashlib.sha256()
        # Match `ledger._hash_payload` keying: basename + null sep + bytes.
        payload_sha.update(Path(payload_rel).name.encode("utf-8"))
        payload_sha.update(b"\0")
        payload_sha.update(current_bytes)
        payload_sha.update(b"\0")
        parts.append("- payload_form: diff")
        parts.append(f"- payload_sha256: `{payload_sha.hexdigest()}`")

    parts += ["", "### Rationale", "", meta["rationale"], "",
              "### candidate.json", "```json",
              (envelope_dir / envelope.CANDIDATE_JSON).read_text(
                  encoding="utf-8").rstrip(), "```"]

    if drift_form:
        # Render unified diff against upstream baseline.
        current_text = (envelope_dir / meta["source_paths"][0]).read_text(
            encoding="utf-8")
        baseline_text = baseline.read_text(encoding="utf-8")
        diff = "".join(difflib.unified_diff(
            baseline_text.splitlines(keepends=True),
            current_text.splitlines(keepends=True),
            fromfile=f"baseline/{meta['drift_target']}",
            tofile=f"consumer/{meta['drift_target']}"))
        parts += ["", "### drift diff (unified, against baseline)",
                  "```diff", diff.rstrip("\n"), "```"]
    else:
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


def gh_command(title: str, body_file: str, labels: list[str],
               repo: str) -> list[str]:
    """Build the `gh issue create` argv for a candidate issue.

    Takes a path to a tempfile holding the body rather than the body
    inline (P-0077): on Windows, `subprocess.run(['gh', ..., '--body',
    body])` exceeds `CreateProcessW`'s ~32K UNICODE_STRING cmdline cap
    for bodies in the 40K+ range, which Python misleadingly surfaces as
    `FileNotFoundError`. Writing the body to a temp file and passing
    `--body-file` sidesteps the cmdline length entirely.
    """
    argv = ["gh", "issue", "create", "--repo", repo,
            "--title", title, "--body-file", body_file]
    for label in labels:
        argv += ["--label", label]
    return argv


def publish_envelope(envelope_dir: Path, candidate_id: str,
                     repo: str = UPSTREAM_REPO) -> str | None:
    """Publish the envelope as a `candidates` prerelease asset (P-0088 Phase 2).

    So the hub's candidate-intake CI can fetch + run the REAL validator/scanner
    against the envelope (not brittle issue-body parsing), the envelope is
    tarred to `<id>.tar.gz` and uploaded (idempotently, `--clobber`) to a single
    `candidates` prerelease on the hub repo.

    Best-effort: any failure is logged and swallowed -- the issue has already
    been created, so a missing release asset only means CI cannot auto-fetch
    (the candidate is then labeled needs-human and a maintainer handles it).
    Returns the asset name on success, or None.

    NOTE: uploading a release asset to `repo` requires write access to that
    repo's releases. The GitHub-issue transport itself needs no write access;
    this publish step degrades gracefully for arms-length consumers who lack it.
    """
    asset = f"{candidate_id}.tar.gz"
    tmp = Path(tempfile.mkdtemp())
    try:
        # archive the envelope CONTENTS (candidate.json + payload/) -> <id>.tar.gz
        shutil.make_archive(str(tmp / candidate_id), "gztar",
                            root_dir=str(envelope_dir))
        # ensure the holding prerelease exists (ignore "already exists")
        subprocess.run(
            ["gh", "release", "create", "candidates", "--repo", repo,
             "--prerelease", "--title", "candidate envelopes (CI intake)",
             "--notes", "Envelope assets for the candidate-intake CI (P-0082)."],
            capture_output=True, text=True)
        # upload / overwrite this candidate's asset
        subprocess.run(
            ["gh", "release", "upload", "candidates", "--repo", repo,
             str(tmp / asset), "--clobber"],
            capture_output=True, text=True, check=True)
        log.info("[uplink] published envelope asset %s", asset)
        return asset
    except (subprocess.CalledProcessError, OSError, FileNotFoundError) as exc:
        log.warning("[uplink] envelope publish skipped (%s); CI auto-fetch "
                    "unavailable for %s -- candidate will be needs-human",
                    exc.__class__.__name__, candidate_id)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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
    if dry_run:
        # No tempfile written for dry-run; show what argv would look like.
        argv_preview = gh_command(title, "<body-file>", labels, repo)
        shown = argv_preview[:-1] + [f"<body {len(body)} chars>"]
        return ("[dry-run] would run:\n  " + " ".join(shown)
                + f"\n\n--- issue title ---\n{title}\n"
                + f"--- issue body ---\n{body}")
    # P-0077: write body to a tempfile and pass --body-file to `gh issue
    # create` so we never hit Windows's CreateProcessW cmdline cap.
    body_file = tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8")
    try:
        body_file.write(body)
        body_file.close()
        argv = gh_command(title, body_file.name, labels, repo)
        try:
            result = subprocess.run(argv, capture_output=True, text=True,
                                    check=True)
        except FileNotFoundError:
            raise UplinkError(
                "`gh` CLI not found -- install GitHub CLI to uplink")
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            # P-0077: a missing kind/<x> or `candidate` label on the hub
            # surfaces as "label not found" -- hint at the fix instead of
            # echoing the bare gh error.
            if "not found" in stderr.lower() and "label" in stderr.lower():
                raise UplinkError(
                    f"gh issue create failed: {stderr}\n"
                    "  Hint: the hub repo is missing a required label. "
                    "Run on the hub:\n"
                    "    gh label create 'candidate' --color D4C5F9\n"
                    "    gh label create 'kind/skill' --color C5DEF5\n"
                    "    gh label create 'kind/hook' --color C5DEF5\n"
                    "    gh label create 'kind/mechanism' --color C5DEF5")
            raise UplinkError(f"gh issue create failed: {stderr}")
    finally:
        Path(body_file.name).unlink(missing_ok=True)
    # P-0088 Phase 2: publish the envelope so the hub's candidate-intake CI can
    # fetch + validate it. Best-effort -- the issue is already created; a
    # publish failure must not fail the uplink.
    publish_envelope(envelope_dir, meta["id"], repo=repo)
    return result.stdout.strip()
