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
import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from governance_core.candidates import collect, envelope

logger = logging.getLogger("governance_core.candidates.ledger")

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


# --- P-0076 Phase 1: ledger self-heal from hub issue history ---------------

# Match a payload fenced block: `### payload/<name>\n```[lang]\n<bytes>\n```
# `[lang]` is empty for skill payloads (uplink writes ``` ); for the
# candidate.json block uplink writes ```json. The capture is non-greedy and
# stops at the first closing fence so multiple payload blocks parse cleanly.
_PAYLOAD_FENCE_RE = re.compile(
    r"^### payload/(?P<name>[^\n]+)\n```[^\n]*\n(?P<content>.*?)\n```",
    re.MULTILINE | re.DOTALL)

_CANDIDATE_JSON_FENCE_RE = re.compile(
    r"^### candidate\.json\n```json\n(?P<content>.*?)\n```",
    re.MULTILINE | re.DOTALL)


def parse_payload_from_issue_body(body: str) -> tuple[dict, dict[str, bytes]]:
    """Parse a candidate issue's body into (candidate_meta, payload_bytes).

    Returns:
        meta: the candidate.json dict embedded under `### candidate.json`.
        payload_bytes: a mapping from `Path(rel).name` to the raw UTF-8
            bytes captured under each `### payload/<name>.md` fenced block.

    Raises `ValueError` if the body lacks a candidate.json block or any
    declared `source_paths` entry has no matching fenced block. The caller
    decides whether to skip-and-log or raise further.

    Used by both `discover_uplinked_from_hub` (Phase 1 ledger recovery) and
    the hub-side `maintainer/reject_candidate.py` (Phase 2 reject feedback)
    -- one parser, one source of truth for the body schema.
    """
    json_match = _CANDIDATE_JSON_FENCE_RE.search(body)
    if not json_match:
        raise ValueError("issue body has no `### candidate.json` block")
    meta = json.loads(json_match.group("content"))
    payload: dict[str, bytes] = {}
    for m in _PAYLOAD_FENCE_RE.finditer(body):
        # `name` is `payload/<basename>` (full relative path under the
        # envelope); the digest function keys on basename, so reduce here.
        rel = m.group("name")
        payload[Path(rel).name] = m.group("content").encode("utf-8")
    for rel in meta["source_paths"] if "source_paths" in meta else []:
        if Path(rel).name not in payload:
            raise ValueError(
                f"issue body declares source_paths={meta['source_paths']!r} "
                f"but `### payload/{rel}` block is missing")
    return meta, payload


def discover_uplinked_from_hub(origin: str,
                               repo: str = "napheir/governance-core",
                               ) -> list[dict[str, Any]]:
    """Rebuild uplink ledger entries from the hub's candidate issue history.

    Queries open + closed `[candidate] ... (from <origin>)` issues via
    `gh issue list --state all`. For each issue: parse the body to recover
    the candidate metadata + payload bytes, recompute `_hash_payload([
    (basename, bytes), ...])`, return one entry per issue ready to feed
    `record_uplink`.

    Recovery is best-effort: any single issue that fails to parse or whose
    body schema does not match (e.g. pre-0.8.0 issues that may have had
    payload trailing whitespace stripped by an earlier uplink.py) is logged
    at INFO and skipped. The caller treats the absence of an entry as
    "ledger unknown" and the regular sweep dedup path still applies.

    Returns `[]` if `gh` is unavailable or the call fails (network /
    auth), so recovery never blocks wrap-up.
    """
    search = f"[candidate] (from {origin})"
    argv = ["gh", "issue", "list", "--repo", repo, "--state", "all",
            "--search", search, "--json", "number,title,body,url",
            "--limit", "200"]
    try:
        result = subprocess.run(argv, capture_output=True, check=True)
    except FileNotFoundError:
        logger.info("[ledger-recovery] `gh` not found; skipping recovery")
        return []
    except subprocess.CalledProcessError as exc:
        logger.info("[ledger-recovery] gh issue list failed: %s",
                    exc.stderr.decode("utf-8", errors="replace").strip()
                    if exc.stderr else "(no stderr)")
        return []
    try:
        issues = json.loads(result.stdout.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        logger.info("[ledger-recovery] gh output not JSON: %s", exc)
        return []

    rebuilt: list[dict[str, Any]] = []
    for issue in issues:
        body = issue["body"] if "body" in issue else ""
        url = issue["url"] if "url" in issue else ""
        number = issue["number"] if "number" in issue else "?"
        try:
            meta, payload = parse_payload_from_issue_body(body)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.info("[ledger-recovery] issue #%s skipped (parse): %s",
                        number, exc)
            continue
        if "id" not in meta:
            logger.info("[ledger-recovery] issue #%s skipped (no id in "
                        "candidate.json)", number)
            continue
        digest = _hash_payload(list(payload.items()))
        rebuilt.append({
            "digest": digest,
            "candidate_id": meta["id"],
            "issue_url": url,
        })
    return rebuilt
