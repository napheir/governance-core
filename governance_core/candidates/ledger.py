"""Uplink ledger: record which candidate envelopes were uplinked (P-0072).

The /wrap-up candidate trigger collects `candidate-common` skills into the
outbox every phase; without a record it would re-uplink the same skill
each time -- and the candidate id is date-stamped, so the id alone does
not dedup across days. The ledger keys on a content digest of the
envelope's payload: an unchanged skill is uplinked once; an edited skill,
having a new digest, is uplinked again as a fresh candidate.

The ledger lives in the consumer-side outbox (`.governance/candidate-
outbox/_uplinked.json`) -- gitignored, like the outbox it sits in.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from governance_core.candidates import collect, envelope

LEDGER_NAME = "_uplinked.json"
LEDGER_SCHEMA = 1


def ledger_path(project_root: Path) -> Path:
    """Return the uplink-ledger path inside the candidate outbox."""
    return collect.outbox_dir(project_root) / LEDGER_NAME


def _hash_payload(items: list[tuple[str, bytes]]) -> str:
    """Return a sha256 over (basename, bytes) pairs, order-stable."""
    digest = hashlib.sha256()
    for name, data in sorted(items):
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def payload_digest(envelope_dir: Path) -> str:
    """Return a sha256 over an envelope's payload files (basename + bytes).

    Keyed on the payload file *basename*, not the envelope-relative path,
    so a loose skill file and the same file inside an envelope's payload/
    hash equal -- letting the SessionStart reminder (P-0072 Phase 2) match
    learned skills against the ledger without rebuilding envelopes. Two
    envelopes with identical payload content hash equal even when their
    date-stamped ids differ.
    """
    meta = envelope.validate_envelope(envelope_dir)
    return _hash_payload([
        (Path(rel).name, (envelope_dir / rel).read_bytes())
        for rel in meta["source_paths"]])


def skill_digest(skill_path: Path) -> str:
    """Return the candidate digest of a loose skill file.

    Equals `payload_digest` of the single-file envelope `collect` would
    build for this skill, so a learned skill can be checked against the
    uplink ledger directly.
    """
    return _hash_payload([(skill_path.name, skill_path.read_bytes())])


def pending_candidate_skills(project_root: Path) -> list[Path]:
    """Return `candidate-common` learned skills not yet in the uplink ledger.

    The query behind the SessionStart reminder hook (P-0072 Phase 2): a
    learned skill tagged `layer: candidate-common` whose content digest is
    absent from the ledger has not been uplinked yet.
    """
    learned = project_root / ".claude" / "skills" / "learned"
    if not learned.exists():
        return []
    led = load_ledger(ledger_path(project_root))
    pending: list[Path] = []
    for skill in sorted(learned.glob("*.md")):
        if collect.read_layer(skill) != "candidate-common":
            continue
        if not is_uplinked(led, skill_digest(skill)):
            pending.append(skill)
    return pending


def load_ledger(path: Path) -> dict[str, Any]:
    """Load the uplink ledger, or return a fresh empty one if absent."""
    if not path.exists():
        return {"schema": LEDGER_SCHEMA, "uplinked": []}
    return json.loads(path.read_text(encoding="utf-8"))


def is_uplinked(ledger: dict[str, Any], digest: str) -> bool:
    """Return True iff an envelope with `digest` was already uplinked."""
    return any(entry["digest"] == digest for entry in ledger["uplinked"])


def record_uplink(path: Path, digest: str, candidate_id: str,
                  issue_url: str) -> None:
    """Append an uplink record to the ledger; idempotent on `digest`."""
    ledger = load_ledger(path)
    if is_uplinked(ledger, digest):
        return
    ledger["uplinked"].append({
        "digest": digest,
        "candidate_id": candidate_id,
        "issue_url": issue_url,
        "uplinked_at": datetime.datetime.now(
            datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
