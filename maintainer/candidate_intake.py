"""Deterministic hub-side candidate/feedback intake (P-0082 Phase 1).

Runs on `issues.opened` via .github/workflows/candidate-intake.yml. It is
deterministic: NO LLM, NO judgment of worth, and -- critically -- NO
promotion. It works from the **embedded candidate.json only** (P-0082 #23):
the metadata always travels in the issue body, so intake needs no payload on
disk and no write to the hub. It only:

  - distinguishes a candidate issue from a free-text feedback issue,
  - validates the embedded candidate.json metadata with the real metadata
    validator (`governance_core.candidates.envelope.validate_metadata`):
    schema / kind / layer / source_paths / drift-field consistency,
  - computes a DETERMINISTIC T0-eligibility hint from metadata alone
    (net-new + kind + layer + security-surface), and
  - applies labels + posts one acknowledgement comment.

The payload-dependent checks (full structural validation, secret re-scan,
rejected-digest dedup) need the payload files on disk, which only exist at
PROMOTE-time -- a rare, hub-side, human/Phase-2-gated moment. They are NOT done
here; they belong in P-0082 Phase 2's `curate_gate.py`. This script never
promotes, so it carries no privilege-escalation surface. The label and
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
from pathlib import Path

from governance_core.candidates import envelope as _envelope
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
# Deterministic helpers (all read candidate.json metadata only)
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


def validate_metadata_ok(meta: dict) -> str | None:
    """Validate the embedded candidate.json metadata; return an error or None.

    Delegates to the real metadata-only validator
    (`envelope.validate_metadata`) -- the same schema/kind/layer/source_paths
    checks the envelope format enforces, minus the payload-on-disk check (which
    needs the payload that only exists at promote-time).
    """
    try:
        _envelope.validate_metadata(meta)
    except _envelope.EnvelopeError as exc:
        return str(exc)
    return None


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


def compute_eligibility(
    *,
    metadata_valid: bool,
    net_new: bool,
    surface_hit: str | None,
    kind: str,
    layer: str,
) -> tuple[list[str], str]:
    """Pure deterministic label + eligibility decision (NO I/O).

    Computed from candidate.json metadata alone (P-0082 #23). This is the
    deterministic core of the intake and the unit-tested seam. Returns
    (labels, eligibility_text). Never returns an `auto-promote` style label --
    the strongest positive signal is `auto-eligible`, which is only a hint for
    the Phase 2 routine (which re-verifies the full gate before any promote).
    """
    if not metadata_valid:
        return ["candidate", "invalid"], "invalid (candidate.json metadata invalid)"
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
        reason = "metadata-only"
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
                "candidate.json.")
        log.info("candidate issue %s -> invalid (unparseable)", issue)
        return 0

    cid = meta.get("id", "?")
    kind = meta.get("kind", "?")
    layer = meta.get("layer", "?")
    raw_paths = meta.get("source_paths", [])
    source_paths = raw_paths if isinstance(raw_paths, list) else []

    # 1. validate the embedded candidate.json metadata only (no payload on disk)
    meta_error = validate_metadata_ok(meta)
    metadata_valid = meta_error is None

    verdicts = [f"id `{cid}`, kind `{kind}`, layer `{layer}`"]
    verdicts.append("candidate.json: VALID (metadata)" if metadata_valid
                    else f"candidate.json: INVALID ({meta_error})")

    # 2. metadata-only T0 inputs (only meaningful when metadata is valid)
    surface_hit: str | None = None
    net_new = True
    if metadata_valid:
        surface_hit = (touches_surface(source_paths, load_surface_globs())
                       if source_paths else None)
        net_new = is_net_new(source_paths) if source_paths else True
        verdicts.append(f"surface: {surface_hit}" if surface_hit
                        else "surface: no deny-set hit")
        verdicts.append("net-new: yes" if net_new
                        else "net-new: no (overwrites tracked)")
        verdicts.append("payload checks (full structural / secret scan / dedup) "
                        "deferred to promote-time")

    labels, eligibility = compute_eligibility(
        metadata_valid=metadata_valid, net_new=net_new,
        surface_hit=surface_hit, kind=kind, layer=layer)

    add_labels(repo, issue, *labels)
    comment(repo, issue,
            "**Intake (deterministic -- no judgment, candidate.json only):**\n\n- "
            + "\n- ".join(verdicts)
            + f"\n- T0-eligibility: **{eligibility}**\n\n"
            "_Promote/advise is decided by the layer-2 curation routine "
            "(P-0082 Phase 2); the full payload checks run there at "
            "promote-time._")
    log.info("candidate %s -> %s", cid, eligibility)
    return 0


if __name__ == "__main__":
    sys.exit(main())
