"""Deterministic auto-promote gate for the curation routine (P-0082 Phase 2).

This is the ONLY thing that may green-light an auto-promote. It is purely
deterministic: the LLM routine calls `evaluate()` and may NEVER override a
`False`. A candidate is auto-promote-eligible ONLY when every check passes AND a
trial-apply of the payload keeps the test suite green.

The payload is NOT published to the hub (P-0089) -- for a net-new candidate the
full payload is embedded in the issue body by `uplink.build_issue`. This gate
reconstructs the envelope from that body, then runs the real validators
(`envelope.validate_envelope`, `uplink.scan_envelope`, the rejected registry)
plus the security-surface + net-new checks reused from `candidate_intake`, plus
a trial-apply. Reconstruction is best-effort and FAILS CLOSED: if the body does
not reconstruct cleanly (e.g. drift/diff form, or a payload that itself contains
``` fences), the gate returns not-eligible and the candidate routes to a human.

Kill-switch: `auto_curate_enabled` ({"enabled": bool}); absent/false/unreadable
=> auto-promote disabled (advise-only). Checked by the routine before calling
the gate; `is_auto_curate_enabled()` is the helper.

CLI (for the routine to call and obey):
    python maintainer/curate_gate.py --issue N --repo owner/name
prints a JSON line: {"eligible": bool, "reasons": [...]}.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from governance_core.candidates import envelope as _envelope
from governance_core.candidates import ledger as _ledger
from governance_core.candidates import registry as _registry
from governance_core.candidates import rejected as _rejected
from governance_core.candidates import uplink as _uplink

# Reuse intake's surface + net-new checks (Art.8: no parallel implementation).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate_intake as _intake  # noqa: E402

KILL_SWITCH = Path(__file__).with_name("auto_curate_enabled")
SURFACE_CONFIG = Path(__file__).with_name("auto_promote_security_surface.json")

# Kinds the auto path may ever promote. The surface model names {skill, doc},
# but the envelope schema KINDS are (skill, hook, mechanism) -- `doc` fails
# metadata validation upstream, so only `skill` is auto-promotable in practice
# (doc-gap, tracked as a follow-up). Gate on what can actually pass.
AUTO_KINDS = {"skill"}

# Package-source placement, mirroring candidate.py promote's dest_of.
DEST_OF = {"skill": "governance_core/skills", "hook": "governance_core/hooks"}


@dataclass
class GateResult:
    """Deterministic verdict; `eligible` is authoritative, LLM cannot override."""
    eligible: bool
    reasons: list[str] = field(default_factory=list)

    def as_json(self) -> str:
        return json.dumps({"eligible": self.eligible, "reasons": self.reasons})


# ---------------------------------------------------------------------------
# Kill-switch
# ---------------------------------------------------------------------------
def is_auto_curate_enabled() -> bool:
    """True only if the kill-switch file explicitly enables auto-promote.

    Fail-closed: a missing / unreadable / malformed file => disabled.
    """
    try:
        return json.loads(KILL_SWITCH.read_text(encoding="utf-8"))["enabled"] is True
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Envelope reconstruction from the issue body
# ---------------------------------------------------------------------------
def _extract_fence(body: str, header: str) -> str | None:
    """Return the content of the fenced block directly under `### <header>`.

    Matches an opening fence with an optional language tag (```json or ```) and
    captures up to the next line that is exactly ```. Returns None if absent.
    """
    pat = re.compile(
        r"^###[ \t]+" + re.escape(header) + r"[ \t]*\n```[a-zA-Z0-9]*\n(.*?)\n```",
        re.DOTALL | re.MULTILINE)
    m = pat.search(body)
    return m.group(1) if m else None


def reconstruct_envelope(body: str, dest_dir: Path) -> Path | None:
    """Rebuild a candidate envelope dir from an issue body, or None.

    Byte-faithful where it can be: payload files are written from the exact
    fenced bytes so a digest computed here matches the one computed at uplink.
    """
    raw = _extract_fence(body, "candidate.json")
    if raw is None:
        return None
    try:
        meta = json.loads(raw)
    except json.JSONDecodeError:
        return None
    source_paths = meta.get("source_paths")
    if not isinstance(source_paths, list) or not source_paths:
        return None
    # A drift/diff-form body carries a diff, not the payload fences -> bail.
    if "drift_target" in meta or "### drift diff" in body:
        return None

    env = dest_dir / "env"
    env.mkdir(parents=True, exist_ok=True)
    (env / _envelope.CANDIDATE_JSON).write_bytes(raw.encode("utf-8"))
    for rel in source_paths:
        content = _extract_fence(body, rel)
        if content is None:
            return None
        target = env / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes (not write_text) to avoid newline translation so the
        # reconstructed payload hashes identically to the original.
        target.write_bytes(content.encode("utf-8"))
    return env


# ---------------------------------------------------------------------------
# Individual deterministic checks
# ---------------------------------------------------------------------------
def _registry_path(project_root: Path) -> Path:
    return project_root / "maintainer" / "consumer_registry.json"


def _is_rejected(env_dir: Path, meta: dict) -> bool:
    """True iff the reconstructed payload matches a blocking rejected entry.

    `meta` is post-`validate_envelope`, so its required keys are present.
    """
    try:
        digest = _ledger.payload_digest(env_dir)
    except (OSError, _envelope.EnvelopeError):
        return False
    reg = _rejected.load_rejected_registry()
    title = meta["title"]
    for name in (title, f"{title}.md"):
        r = _rejected.is_rejected(name, digest, reg)
        if r is not None and _rejected.should_block(r):
            return True
    return False


def _skill_theme_hold(env_dir: Path, meta: dict) -> str | None:
    """For a skill candidate, hold if its frontmatter theme/tags are governed.

    Reads the skill .md payload's frontmatter `theme:` + `tags:` and compares
    against the surface config's skill_theme_supplement hold-sets. Returns a
    reason string to hold, or None. `meta` is post-validation.
    """
    if meta["kind"] != "skill":
        return None
    try:
        cfg = json.loads(SURFACE_CONFIG.read_text(encoding="utf-8"))
        supp = cfg["skill_theme_supplement"]
        hold_themes = set(supp["hold_if_theme_in"])
        hold_tags = set(supp["hold_if_tags_intersect"])
    except (OSError, json.JSONDecodeError, KeyError):
        return None
    for rel in meta["source_paths"]:
        p = env_dir / rel
        if p.suffix != ".md" or not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        fm = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
        block = fm.group(1) if fm else text[:2000]
        tm = re.search(r"^theme:[ \t]*([A-Za-z0-9_-]+)", block, re.MULTILINE)
        if tm and tm.group(1) in hold_themes:
            return f"theme={tm.group(1)}"
        tagm = re.search(r"^tags:[ \t]*\[([^\]]*)\]", block, re.MULTILINE)
        if tagm:
            tags = {t.strip().strip("'\"") for t in tagm.group(1).split(",")}
            inter = tags & hold_tags
            if inter:
                return f"tags={sorted(inter)}"
    return None


def trial_apply(env_dir: Path, meta: dict, project_root: Path) -> tuple[bool, str]:
    """Place the (net-new) payload at its target, run pytest, then remove it.

    The candidate is already known net-new (the gate checks this first), so the
    placed files overwrite nothing -- cleanup is a plain unlink, leaving the
    checkout exactly as found. Runs in the live checkout on purpose: the
    editable install resolves to this checkout, so pytest sees the placed files.
    Returns (green, detail).
    """
    if meta["kind"] not in DEST_OF:
        return False, f"no placement for kind={meta['kind']}"
    dest = project_root / DEST_OF[meta["kind"]]
    placed: list[Path] = []
    try:
        dest.mkdir(parents=True, exist_ok=True)
        for rel in meta["source_paths"]:
            tgt = dest / Path(rel).name
            if tgt.exists():  # defensive: should be net-new
                return False, f"target already exists: {tgt.name}"
            tgt.write_bytes((env_dir / rel).read_bytes())
            placed.append(tgt)
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tools/", "-q"],
            cwd=str(project_root), capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            return True, "pytest green"
        return False, f"pytest red (rc={proc.returncode})"
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"trial error: {exc}"
    finally:
        for p in placed:
            try:
                p.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------
def evaluate(issue_body: str, *, project_root: Path | None = None,
            run_trial: bool = True) -> GateResult:
    """Deterministic auto-promote verdict for one candidate issue body.

    Returns GateResult(eligible, reasons). Any failing check => not eligible.
    The LLM routine MUST obey a False; it may only downgrade an eligible
    candidate (relabel needs-human), never upgrade past a False.
    """
    root = project_root or Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        env = reconstruct_envelope(issue_body, Path(tmp))
        if env is None:
            return GateResult(False, ["envelope not reconstructable from body "
                                      "(drift/diff form or malformed payload)"])
        try:
            meta = _envelope.validate_envelope(env)
        except _envelope.EnvelopeError as exc:
            return GateResult(False, [f"envelope invalid: {exc}"])

        if _registry.is_consumer_revoked(_registry_path(root), meta["origin"]):
            return GateResult(False, [f"origin {meta['origin']!r} is revoked"])
        if _uplink.scan_envelope(env):
            return GateResult(False, ["secret found in payload (re-scan)"])
        if _is_rejected(env, meta):
            return GateResult(False, ["matches a previously-rejected candidate"])
        if meta["kind"] not in AUTO_KINDS:
            return GateResult(False, [f"kind={meta['kind']!r} not auto-promotable "
                                      f"(auto kinds: {sorted(AUTO_KINDS)})"])
        if meta["layer"] != "candidate-common":
            return GateResult(False, [f"layer={meta['layer']!r} not candidate-common"])
        if not _intake.is_net_new(meta["source_paths"]):
            return GateResult(False, ["not net-new (overwrites a tracked file)"])
        hit = _intake.touches_surface(meta["source_paths"], _intake.load_surface_globs())
        if hit:
            return GateResult(False, [f"security-surface hit: {hit}"])
        theme = _skill_theme_hold(env, meta)
        if theme:
            return GateResult(False, [f"skill theme/tags held: {theme}"])

        if run_trial:
            ok, detail = trial_apply(env, meta, root)
            if not ok:
                return GateResult(False, [f"trial-apply failed: {detail}"])
            return GateResult(True, [f"all checks passed; trial-apply: {detail}"])
        return GateResult(True, ["all deterministic checks passed (trial skipped)"])


def _fetch_issue_body(repo: str, issue: str) -> str:
    out = subprocess.run(
        ["gh", "issue", "view", issue, "--repo", repo, "--json", "body",
         "--jq", ".body"],
        capture_output=True, text=True, check=True)
    return out.stdout


def main() -> int:
    """CLI: fetch an issue body, evaluate the gate, print a JSON verdict."""
    parser = argparse.ArgumentParser(prog="curate_gate")
    parser.add_argument("--issue", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--no-trial", action="store_true",
                        help="skip trial-apply (deterministic checks only)")
    args = parser.parse_args()
    body = _fetch_issue_body(args.repo, args.issue)
    result = evaluate(body, project_root=Path(args.project_root).resolve(),
                      run_trial=not args.no_trial)
    sys.stdout.write(result.as_json() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
