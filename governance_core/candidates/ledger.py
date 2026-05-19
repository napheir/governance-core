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


def payload_digest(envelope_dir: Path) -> str:
    """Return a sha256 over an envelope's payload files (order-stable).

    The digest covers each declared source path and its bytes, so two
    envelopes with identical payload content hash equal even when their
    date-stamped ids differ.
    """
    meta = envelope.validate_envelope(envelope_dir)
    digest = hashlib.sha256()
    for rel in sorted(meta["source_paths"]):
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update((envelope_dir / rel).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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
