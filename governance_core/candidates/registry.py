"""Consumer + candidate registry for governance-core (P-0065 Phase 5).

The hub-side ledger of the candidate pipeline:

  - **consumers** -- every authorization code the maintainer has issued
    (consumer_id, issue date, optional expiry). `issue_auth_code.py` appends
    here on each issuance.
  - **candidates** -- every candidate the maintainer has reviewed, with its
    curation decision (promoted / rejected / override) and a note.

The registry is a single committed JSON file (`maintainer/consumer_registry.json`)
-- maintainer-side, alongside the signing tools, and the durable record of
who is authorized and what has been curated.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = 1
DECISIONS = ("promoted", "rejected", "override")


def _now() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _empty() -> dict[str, Any]:
    """Return a fresh, empty registry structure."""
    return {"schema": REGISTRY_SCHEMA, "consumers": [], "candidates": []}


def load_registry(path: Path) -> dict[str, Any]:
    """Load the registry file, or return an empty registry if absent."""
    if not path.exists():
        return _empty()
    return json.loads(path.read_text(encoding="utf-8"))


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    """Persist `registry` to `path` as pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def record_consumer(path: Path, consumer_id: str, issued: str,
                    expiry: str | None = None, note: str = "") -> None:
    """Append (or refresh) a consumer entry in the registry.

    Re-issuing for an existing consumer_id replaces that entry rather than
    duplicating it.
    """
    registry = load_registry(path)
    entry = {"consumer_id": consumer_id, "issued": issued,
             "expiry": expiry, "note": note, "recorded_at": _now()}
    registry["consumers"] = [c for c in registry["consumers"]
                             if c["consumer_id"] != consumer_id]
    registry["consumers"].append(entry)
    registry["consumers"].sort(key=lambda c: c["consumer_id"])
    save_registry(path, registry)


def record_candidate(path: Path, candidate_id: str, origin: str, kind: str,
                     title: str, decision: str, note: str = "") -> None:
    """Append (or refresh) a curated-candidate entry in the registry."""
    if decision not in DECISIONS:
        raise ValueError(f"decision must be one of {DECISIONS}, got "
                         f"{decision!r}")
    registry = load_registry(path)
    entry = {"id": candidate_id, "origin": origin, "kind": kind,
             "title": title, "decision": decision, "note": note,
             "reviewed_at": _now()}
    registry["candidates"] = [c for c in registry["candidates"]
                              if c["id"] != candidate_id]
    registry["candidates"].append(entry)
    save_registry(path, registry)
