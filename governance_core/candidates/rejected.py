"""Rejected candidate registry: hub -> consumer reject feedback (P-0076 Phase 2).

The hub maintains `rejected_registry.json` (committed in package source,
shipped in every wheel). Each entry records a previously-rejected candidate
skill -- its name, the payload digest at reject time, the reason the hub
gave, and the advice the consumer's owner should follow (typically: drop
`layer: candidate-common`, keep as a local learned skill, or delete).

Consumer-side sweep consults `is_rejected(name, sha)` before uplinking a
candidate-common skill. Three outcomes:

  - exact match (sha equal)  -> uplink blocked, structured advisory printed
  - name match (sha differs) -> if `block_by_name` is true on the entry,
                                also blocked (intended for pre-Phase-1
                                backfill where the sha could not be
                                preserved); otherwise warn but allow uplink
                                so the hub re-evaluates the new content
  - no match                 -> normal collect/uplink path

The mechanism is advisory: nothing in this module modifies a consumer's
skill files. The aim is owner awareness, not control.

Registry shipped in the wheel; updates land via `pip install -U
governance-core` (the existing `update-reminder.py` SessionStart hook
prompts consumers within ~12h of a new release).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("governance_core.candidates.rejected")

REGISTRY_REL = "rejected_registry.json"


def registry_path() -> Path:
    """Return the path to the wheel-shipped rejected registry."""
    return Path(__file__).resolve().parent / REGISTRY_REL


def load_rejected_registry() -> dict[str, Any]:
    """Load `rejected_registry.json` from the package. Fail-safe: any read
    or JSON error logs and returns an empty registry shape, so consumer
    sweep never breaks on a malformed registry.
    """
    path = registry_path()
    if not path.exists():
        return {"schema": 1, "rejected": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.info("[rejected] could not load registry: %s -- "
                    "treating as empty", exc)
        return {"schema": 1, "rejected": []}


def is_rejected(skill_name: str, payload_sha256: str,
                registry: dict[str, Any] | None = None,
                ) -> dict[str, Any] | None:
    """Check whether a (name, sha) pair was previously rejected by the hub.

    Returns:
        None if the skill is not in the registry (proceed normally).
        {"match": "exact", "entry": <entry dict>} if the registry has an
            entry whose `payload_sha256` equals the given sha -- the same
            content was previously rejected; sweep BLOCKS uplink.
        {"match": "name", "entry": <entry dict>} if the registry has an
            entry with the same `skill_name` but a different (or null)
            sha. The entry's `block_by_name` field controls whether sweep
            BLOCKS (true) or WARNS-AND-ALLOWS (false, the default) -- the
            caller inspects `entry["block_by_name"]` to decide.

    If `registry` is None, loads via `load_rejected_registry`.
    """
    if registry is None:
        registry = load_rejected_registry()
    name_match: dict[str, Any] | None = None
    for entry in registry["rejected"]:
        if entry["skill_name"] != skill_name:
            continue
        entry_sha = entry["payload_sha256"] if "payload_sha256" in entry \
            else None
        if entry_sha is not None and entry_sha == payload_sha256:
            return {"match": "exact", "entry": entry}
        # remember the first name-match in case no exact match later
        if name_match is None:
            name_match = {"match": "name", "entry": entry}
    return name_match


def should_block(rejection: dict[str, Any]) -> bool:
    """Return True iff the rejection result requires blocking uplink.

    `exact` always blocks. `name` blocks only when the entry sets
    `block_by_name: true` (the maintainer's signal that this rejection
    applies to the name regardless of payload edits -- used for pre-
    Phase-1 backfill where the original sha was unrecoverable).
    """
    if rejection["match"] == "exact":
        return True
    entry = rejection["entry"]
    return ("block_by_name" in entry and entry["block_by_name"] is True)


def format_advisory(skill_name: str, rejection: dict[str, Any]) -> str:
    """Build the multi-line advisory string sweep prints for a rejected skill."""
    entry = rejection["entry"]
    kind = "previously rejected by hub" if rejection["match"] == "exact" \
        else ("a previously-rejected skill with the same name exists "
              "(different content)")
    lines = [
        f"  reason:   {entry['reason'] if 'reason' in entry else '(no reason recorded)'}",
        f"  advice:   {entry['advice'] if 'advice' in entry else '(no advice recorded)'}",
    ]
    if "issue_urls" in entry and entry["issue_urls"]:
        lines.append("  issues:   " + entry["issue_urls"][0])
        for url in entry["issue_urls"][1:]:
            lines.append("            " + url)
    header = f"[candidate] {skill_name} -- {kind}"
    return header + "\n" + "\n".join(lines)
