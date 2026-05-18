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

REGISTRY_SCHEMA = 2
DECISIONS = ("promoted", "rejected", "override")


def _now() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _empty() -> dict[str, Any]:
    """Return a fresh, empty registry structure."""
    return {"schema": REGISTRY_SCHEMA, "consumers": [], "candidates": []}


def _migrate(registry: dict[str, Any]) -> dict[str, Any]:
    """Bring an older registry up to REGISTRY_SCHEMA in memory (P-0071).

    Schema 2 adds per-consumer `status` / `first_issued` / `last_issued`.
    A schema-1 entry is filled in place: `status` is inferred (`revoked`
    if it already carries a `revoked_on`, else `active`), and the issue
    dates default from the old single `issued` field.
    """
    schema = registry["schema"] if "schema" in registry else 1
    if schema >= REGISTRY_SCHEMA:
        return registry
    for entry in registry["consumers"]:
        if "status" not in entry:
            entry["status"] = "revoked" if "revoked_on" in entry else "active"
        issued = entry["issued"] if "issued" in entry else None
        if "first_issued" not in entry:
            entry["first_issued"] = issued
        if "last_issued" not in entry:
            entry["last_issued"] = issued
    registry["schema"] = REGISTRY_SCHEMA
    return registry


def load_registry(path: Path) -> dict[str, Any]:
    """Load the registry file, or return an empty registry if absent.

    An older-schema registry is migrated in memory on load (see _migrate);
    the migrated form is persisted on the next save_registry.
    """
    if not path.exists():
        return _empty()
    return _migrate(json.loads(path.read_text(encoding="utf-8")))


def save_registry(path: Path, registry: dict[str, Any]) -> None:
    """Persist `registry` to `path` as pretty JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def record_consumer(path: Path, consumer_id: str, issued: str,
                    expiry: str | None = None, note: str = "") -> None:
    """Append (or refresh) a consumer entry in the registry (schema 2).

    Re-issuing for an existing consumer_id replaces that entry rather than
    duplicating it: `first_issued` is preserved from the prior entry,
    `last_issued` is set to this issuance, and `status` returns to
    `active` (issuing a code is an authorization act). If the consumer was
    on the revocation feed, the maintainer must also clear it there --
    there is no auto-unrevoke.
    """
    registry = load_registry(path)
    prior = next((c for c in registry["consumers"]
                  if c["consumer_id"] == consumer_id), None)
    first_issued = (prior["first_issued"]
                    if prior is not None and "first_issued" in prior
                    else issued)
    entry = {"consumer_id": consumer_id, "status": "active",
             "first_issued": first_issued, "last_issued": issued,
             "expiry": expiry, "note": note, "recorded_at": _now()}
    registry["consumers"] = [c for c in registry["consumers"]
                             if c["consumer_id"] != consumer_id]
    registry["consumers"].append(entry)
    registry["consumers"].sort(key=lambda c: c["consumer_id"])
    save_registry(path, registry)


def mark_revoked(path: Path, consumer_id: str, revoked_on: str,
                 reason: str = "") -> bool:
    """Mark a consumer entry as revoked; return True iff the entry existed.

    Sets `status='revoked'`, `revoked_on`, and `revocation_reason` on the
    matching consumer entry (P-0071 Phase 2 -- the registry's revocation
    side; Phase 4 extends the consumer schema further). A consumer absent
    from the registry yields False and changes nothing; the caller decides
    whether that is an error (revoking a never-issued id is a no-op here).
    """
    registry = load_registry(path)
    found = False
    for entry in registry["consumers"]:
        if entry["consumer_id"] == consumer_id:
            entry["status"] = "revoked"
            entry["revoked_on"] = revoked_on
            entry["revocation_reason"] = reason
            found = True
    if found:
        save_registry(path, registry)
    return found


def is_consumer_revoked(path: Path, consumer_id: str) -> bool:
    """Return True iff the registry marks `consumer_id` as revoked.

    A consumer absent from the registry, or one with no `status`, counts
    as not revoked -- only an explicit `status: revoked` blocks (P-0071
    Phase 4: the hub-side check that rejects candidates from a revoked
    origin).
    """
    registry = load_registry(path)
    for entry in registry["consumers"]:
        if entry["consumer_id"] == consumer_id:
            return "status" in entry and entry["status"] == "revoked"
    return False


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
