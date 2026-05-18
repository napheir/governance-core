"""Candidate envelope: format, builder, validator (P-0065 Phase 3).

A candidate envelope is a directory:

    <candidate-id>/
        candidate.json     metadata
        payload/           the actual files (skill .md / hook .py / ...)

`candidate.json` carries:

    schema          envelope schema version (int)
    id              cand-<origin>-<YYYYMMDD>-<slug>
    kind            "skill" | "hook" | "mechanism"
    origin          consumer_id of the project that produced the candidate
    created         ISO-8601 timestamp
    layer           "candidate-common" | "business"
    title           short human title
    rationale       why this is a common-layer candidate
    source_paths    envelope-relative payload paths (e.g. "payload/foo.md")
    drift_target    optional: the install-managed path a drift candidate edits
    baseline_sha256 optional: the manifest baseline of that path

`drift_target` and `baseline_sha256` are present together (a drift-sourced
candidate) or both absent (a net-new / actively-submitted candidate).
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path
from typing import Any

ENVELOPE_SCHEMA = 1
KINDS = ("skill", "hook", "mechanism")
LAYERS = ("candidate-common", "business")
CANDIDATE_JSON = "candidate.json"
PAYLOAD_DIR = "payload"
_REQUIRED = ("schema", "id", "kind", "origin", "created", "layer",
             "title", "rationale", "source_paths")


class EnvelopeError(Exception):
    """Raised when a candidate envelope is malformed or fails validation."""


def _slugify(text: str) -> str:
    """Reduce `text` to a short kebab-case slug for a candidate id."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40] or "candidate"


def make_candidate_id(origin: str, title: str,
                      today: str | None = None) -> str:
    """Build a candidate id: cand-<origin>-<YYYYMMDD>-<title-slug>."""
    day = (today or datetime.date.today().isoformat()).replace("-", "")
    return f"cand-{_slugify(origin)}-{day}-{_slugify(title)}"


def validate_metadata(meta: dict[str, Any]) -> None:
    """Validate a candidate.json metadata dict; raise EnvelopeError if bad."""
    missing = [k for k in _REQUIRED if k not in meta]
    if missing:
        raise EnvelopeError(f"candidate.json missing keys: {missing}")
    if meta["schema"] != ENVELOPE_SCHEMA:
        raise EnvelopeError(
            f"unsupported envelope schema: {meta['schema']!r} "
            f"(expected {ENVELOPE_SCHEMA})")
    if meta["kind"] not in KINDS:
        raise EnvelopeError(
            f"invalid kind: {meta['kind']!r} (expected one of {KINDS})")
    if meta["layer"] not in LAYERS:
        raise EnvelopeError(
            f"invalid layer: {meta['layer']!r} (expected one of {LAYERS})")
    if not isinstance(meta["source_paths"], list) or not meta["source_paths"]:
        raise EnvelopeError("source_paths must be a non-empty list")
    if ("drift_target" in meta) != ("baseline_sha256" in meta):
        raise EnvelopeError(
            "drift_target and baseline_sha256 must be present together "
            "(drift candidate) or both absent")


def validate_envelope(envelope_dir: Path) -> dict[str, Any]:
    """Validate an envelope directory; return its metadata.

    Checks candidate.json is present and valid and that every declared
    source_path exists inside the envelope. Raises EnvelopeError on failure.
    """
    meta_path = envelope_dir / CANDIDATE_JSON
    if not meta_path.exists():
        raise EnvelopeError(f"no {CANDIDATE_JSON} in {envelope_dir}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EnvelopeError(f"{CANDIDATE_JSON} is not valid JSON: {exc}")
    validate_metadata(meta)
    for rel in meta["source_paths"]:
        if not (envelope_dir / rel).exists():
            raise EnvelopeError(f"declared source path missing: {rel}")
    return meta


def build_envelope(
    parent_dir: Path,
    kind: str,
    origin: str,
    title: str,
    rationale: str,
    payload_files: list[Path],
    layer: str = "candidate-common",
    drift_target: str | None = None,
    baseline_sha256: str | None = None,
) -> Path:
    """Create a candidate envelope under `parent_dir`; return its directory.

    Copies `payload_files` into `<id>/payload/` and writes candidate.json.
    Inputs are validated before anything is written; the finished envelope is
    re-validated before return. Raises EnvelopeError on invalid input.
    """
    if kind not in KINDS:
        raise EnvelopeError(f"invalid kind: {kind!r}")
    if layer not in LAYERS:
        raise EnvelopeError(f"invalid layer: {layer!r}")
    if not payload_files:
        raise EnvelopeError("payload_files must not be empty")
    names = [f.name for f in payload_files]
    if len(names) != len(set(names)):
        raise EnvelopeError("payload files have duplicate names")
    if (drift_target is None) != (baseline_sha256 is None):
        raise EnvelopeError(
            "drift_target and baseline_sha256 must be given together")

    candidate_id = make_candidate_id(origin, title)
    envelope_dir = parent_dir / candidate_id
    payload_dir = envelope_dir / PAYLOAD_DIR
    payload_dir.mkdir(parents=True, exist_ok=True)

    source_paths = []
    for src in payload_files:
        shutil.copy2(src, payload_dir / src.name)
        source_paths.append(f"{PAYLOAD_DIR}/{src.name}")

    meta: dict[str, Any] = {
        "schema": ENVELOPE_SCHEMA,
        "id": candidate_id,
        "kind": kind,
        "origin": origin,
        "created": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "layer": layer,
        "title": title,
        "rationale": rationale,
        "source_paths": sorted(source_paths),
    }
    if drift_target is not None:
        meta["drift_target"] = drift_target
        meta["baseline_sha256"] = baseline_sha256

    (envelope_dir / CANDIDATE_JSON).write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    validate_envelope(envelope_dir)
    return envelope_dir
