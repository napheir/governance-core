"""Deterministic hub-side candidate/feedback intake (P-0082 Phase 1).

Runs on `issues.opened` via .github/workflows/candidate-intake.yml. It is
deterministic: NO LLM, NO judgment of worth, and -- critically -- NO
promotion. It only:

  - distinguishes a candidate issue from a free-text feedback issue,
  - fetches the published candidate envelope and structurally validates it
    with the real validator (`governance_core.candidates.envelope`),
  - re-runs the SAME secret scanner the uplink gate uses
    (`governance_core.candidates.uplink.scan_envelope`) -- no parallel scanner,
  - dedups the payload digest against the rejected registry,
  - computes a DETERMINISTIC T0-eligibility hint (net-new + kind + layer +
    security surface), and
  - applies labels + posts one acknowledgement comment.

The promote/advise judgment is P-0082 Phase 2's scheduled routine; this script
never promotes, so it carries no privilege-escalation surface. The label and
eligibility outputs are advisory: a human (or the Phase 2 routine) decides.

Target-path resolution (surface hit + net-new) is best-effort in Phase 1 and
purely informational -- Phase 2 re-derives it authoritatively before any
promote. See `auto_promote_security_surface.json` for the deny-set model.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from governance_core.candidates import envelope as _envelope
from governance_core.candidates import ledger as _ledger
from governance_core.candidates import rejected as _rejected
from governance_core.candidates import uplink as _uplink
from governance_core.tools._classify_match import match as _glob_match

logging.basicConfig(level=logging.INFO, format="[intake] %(message)s")
log = logging.getLogger("candidate_intake")

SURFACE_CONFIG = Path(__file__).with_name("auto_promote_security_surface.json")

# kinds that may ever be T0-auto-eligible (the rest always route to a human)
T0_KINDS = {"skill", "doc"}


# ---------------------------------------------------------------------------
# gh side effects (label + comment) -- thin wrappers, mocked in unit tests
# ---------------------------------------------------------------------------
def gh(*args: str) -> str:
    """Run a gh subcommand, returning stdout (raises on non-zero)."""
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          check=True).stdout


def add_labels(repo: str, issue: str, *labels: str) -> None:
    """Add one or more labels to the issue (single gh call)."""
    args: list[str] = []
    for lab in labels:
        args += ["--add-label", lab]
    gh("issue", "edit", issue, "--repo", repo, *args)


def comment(repo: str, issue: str, body_md: str) -> None:
    """Post a single acknowledgement comment on the issue."""
    gh("issue", "comment", issue, "--repo", repo, "--body", body_md)


# ---------------------------------------------------------------------------
# Deterministic helpers
# ---------------------------------------------------------------------------
def parse_candidate_json(body: str) -> dict | None:
    """Extract and parse the ```json candidate.json block from an issue body."""
    m = re.search(r"###\s*candidate\.json\s*```json\s*(\{.*?\})\s*```",
                  body, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def is_feedback_issue(title: str, body: str) -> bool:
    """True for a free-text feedback issue (no candidate envelope)."""
    return "### candidate.json" not in body and not title.startswith("[candidate]")


def fetch_envelope(repo: str, candidate_id: str) -> Path | None:
    """Download + extract the published envelope for `candidate_id`.

    Mirrors the uplink publish channel (P-0088 Phase 2): the envelope is an
    asset named `<id>.tar.gz` on the `candidates` prerelease. Returns the
    envelope dir (the one containing candidate.json), or None if unavailable.
    """
    tmp = Path(tempfile.mkdtemp())
    asset = f"{candidate_id}.tar.gz"
    try:
        gh("release", "download", "candidates", "--repo", repo,
           "-p", asset, "-D", str(tmp))
        subprocess.run(["tar", "-xzf", str(tmp / asset), "-C", str(tmp)],
                       check=True, capture_output=True)
    except subprocess.CalledProcessError:
        return None
    cand = next(tmp.rglob("candidate.json"), None)
    return cand.parent if cand else None


def load_surface_globs() -> list[str]:
    """Flatten every deny-set glob from the security-surface config."""
    cfg = json.loads(SURFACE_CONFIG.read_text(encoding="utf-8"))
    return [g for body in cfg["categories"].values() for g in body["globs"]]


def _target_path(source_path: str) -> str:
    """Normalize an envelope source_path to a repo-relative target for matching.

    Envelope payloads are declared `payload/<name>`; strip that prefix so the
    surface globs and net-new check see the bare target path. Best-effort
    (Phase 1, informational only).
    """
    norm = source_path.replace("\\", "/")
    return norm[len("payload/"):] if norm.startswith("payload/") else norm


def _match_forms(source_path: str) -> list[str]:
    """The path forms to test against deny-set globs / HEAD.

    A candidate may declare a target-relative path (`tools/x-guard.py`) or an
    envelope-internal one (`payload/x-guard.py`). Test BOTH the raw and the
    `payload/`-stripped form so prefix-globs match the former and `**/`-globs
    match the latter. Target-path resolution is best-effort in Phase 1
    (informational); Phase 2 re-derives it authoritatively before any promote.
    """
    raw = source_path.replace("\\", "/")
    stripped = _target_path(source_path)
    return [raw] if stripped == raw else [raw, stripped]


def touches_surface(source_paths: list[str], globs: list[str]) -> str | None:
    """Return the first `path ~ glob` hit against the deny-set, or None."""
    for p in source_paths:
        for form in _match_forms(p):
            for g in globs:
                if _glob_match(form, g):
                    return f"{form} ~ {g}"
    return None


def is_net_new(source_paths: list[str]) -> bool:
    """True iff no declared target overwrites a gc-tracked file at HEAD.

    `git cat-file -e HEAD:<path>` exits 0 when the path exists in the tree.
    Best-effort: a git failure (not a clean exit-1) is treated as net-new.
    """
    for p in source_paths:
        for form in _match_forms(p):
            result = subprocess.run(
                ["git", "cat-file", "-e", f"HEAD:{form}"],
                capture_output=True, text=True)
            if result.returncode == 0:
                return False
    return True


def is_rejected_dup(env_dir: Path, meta: dict) -> bool:
    """True iff the payload digest matches a blocking rejected-registry entry."""
    try:
        digest = _ledger.payload_digest(env_dir)
    except (OSError, _envelope.EnvelopeError):
        return False
    reg = _rejected.load_rejected_registry()
    title = meta.get("title", "")
    for name in (title, f"{title}.md"):
        r = _rejected.is_rejected(name, digest, reg)
        if r is not None and _rejected.should_block(r):
            return True
    return False


def compute_eligibility(
    *,
    structural_ok: bool,
    secrets_found: bool,
    is_dup: bool,
    net_new: bool,
    surface_hit: str | None,
    kind: str,
    layer: str,
) -> tuple[list[str], str]:
    """Pure deterministic label + eligibility decision (NO I/O).

    This is the deterministic core of the intake and the unit-tested seam.
    Returns (labels, eligibility_text). Never returns an `auto-promote` style
    label -- the strongest positive signal is `auto-eligible`, which is only a
    hint for the Phase 2 routine.
    """
    if not structural_ok:
        return ["candidate", "invalid", "needs-human"], "invalid (envelope not structurally valid)"
    if secrets_found:
        return ["candidate", "invalid", "needs-human"], "invalid (secret found on re-scan)"
    if is_dup:
        return ["candidate", "valid", "dup-of-rejected", "needs-human"], \
            "needs-human (matches a previously-rejected payload)"
    t0 = (net_new and kind in T0_KINDS and layer == "candidate-common"
          and surface_hit is None)
    if t0:
        return ["candidate", "valid", "auto-eligible"], "auto-eligible (T0)"
    if surface_hit is not None:
        reason = f"touches security surface ({surface_hit})"
    elif kind not in T0_KINDS:
        reason = f"kind={kind} not in {sorted(T0_KINDS)}"
    elif not net_new:
        reason = "not net-new (overwrites a tracked file)"
    elif layer != "candidate-common":
        reason = f"layer={layer}"
    else:
        reason = "structural-only"
    return ["candidate", "valid", "needs-human"], f"needs-human ({reason})"


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main() -> int:
    """Run intake for one opened issue; apply labels + post one ack comment."""
    repo = os.environ["GH_REPO"]
    issue = os.environ["ISSUE_NUMBER"]
    title = os.environ.get("ISSUE_TITLE", "")
    body = os.environ.get("ISSUE_BODY", "")

    if is_feedback_issue(title, body):
        add_labels(repo, issue, "feedback", "needs-human")
        comment(repo, issue,
                "**Intake (deterministic):** free-text feedback issue, no "
                "envelope. Labeled `needs-human` for layer-2 (LLM advise + "
                "human).")
        log.info("feedback issue %s -> needs-human", issue)
        return 0

    meta = parse_candidate_json(body)
    if meta is None:
        add_labels(repo, issue, "candidate", "invalid")
        comment(repo, issue,
                "**Intake (deterministic):** could not parse the candidate.json "
                "block. Labeled `invalid` -- re-submit with a well-formed "
                "envelope.")
        log.info("candidate issue %s -> invalid (unparseable)", issue)
        return 0

    cid = meta.get("id", "?")
    kind = meta.get("kind", "?")
    layer = meta.get("layer", "?")
    source_paths = meta.get("source_paths", [])

    verdicts = [f"id `{cid}`, kind `{kind}`, layer `{layer}`"]

    # 1. structural validation against the fetched, published envelope
    env_dir = fetch_envelope(repo, cid)
    structural_ok = False
    secrets_found = False
    is_dup = False
    if env_dir is None:
        verdicts.append("envelope: NOT FETCHABLE (publish missing?) -- INVALID")
    else:
        try:
            _envelope.validate_envelope(env_dir)
            structural_ok = True
            verdicts.append("envelope: VALID")
        except _envelope.EnvelopeError as exc:
            verdicts.append(f"envelope: INVALID ({exc})")

        if structural_ok:
            # 2. secret re-scan -- the SAME HIGH+MEDIUM gate uplink uses
            findings = _uplink.scan_envelope(env_dir)
            secrets_found = bool(findings)
            verdicts.append("secrets: FOUND" if secrets_found
                            else "secrets: clean (re-scan)")
            # 3. dedup vs rejected registry
            is_dup = is_rejected_dup(env_dir, meta)
            verdicts.append("dedup: previously-rejected" if is_dup
                            else "dedup: not a rejected digest")

    # 4. deterministic T0-eligibility hint (informational)
    surface_hit = (touches_surface(source_paths, load_surface_globs())
                   if source_paths else None)
    net_new = is_net_new(source_paths) if source_paths else True
    verdicts.append(f"surface: {surface_hit}" if surface_hit
                    else "surface: no deny-set hit")
    verdicts.append("net-new: yes" if net_new else "net-new: no (overwrites tracked)")

    labels, eligibility = compute_eligibility(
        structural_ok=structural_ok, secrets_found=secrets_found,
        is_dup=is_dup, net_new=net_new, surface_hit=surface_hit,
        kind=kind, layer=layer)

    add_labels(repo, issue, *labels)
    comment(repo, issue,
            "**Intake (deterministic -- no judgment):**\n\n- "
            + "\n- ".join(verdicts)
            + f"\n- T0-eligibility: **{eligibility}**\n\n"
            "_Promote/advise is decided by the layer-2 curation routine "
            "(P-0082 Phase 2)._")
    log.info("candidate %s -> %s", cid, eligibility)
    return 0


if __name__ == "__main__":
    sys.exit(main())
