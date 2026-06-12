"""Candidate collection: outbox location + net-new skill scan (P-0065 Phase 4).

The consumer-side outbox is the pre-uplink staging area for candidate
envelopes -- gitignored, transient. `collect_netnew_skills` is one of the
three candidate sources (the others are drift capture in the installer and
the active `/submit-candidate` flow).
"""

from __future__ import annotations

import re
from pathlib import Path

from governance_core.candidates import envelope

OUTBOX_REL = ".governance/candidate-outbox"


def outbox_dir(project_root: Path) -> Path:
    """Return the consumer-side pre-uplink staging directory."""
    return project_root / OUTBOX_REL


def read_layer(skill_path: Path) -> str | None:
    """Return the `layer:` frontmatter value of a skill file, or None."""
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        return None
    block = re.search(r"^---\s*$(.*?)^---\s*$", text,
                      re.MULTILINE | re.DOTALL)
    if not block:
        return None
    line = re.search(r"^layer:\s*(\S+)\s*$", block.group(1), re.MULTILINE)
    return line.group(1) if line else None


def collect_netnew_skills(project_root: Path, origin: str) -> list[Path]:
    """Package every `layer: candidate-common` learned skill as an envelope.

    Scans `.claude/skills/learned/`; each skill tagged candidate-common is
    built into a `kind: skill` candidate envelope under the outbox. Returns
    the envelope directories created.
    """
    learned = project_root / ".claude" / "skills" / "learned"
    if not learned.exists():
        return []
    # Lazy import: ledger imports collect at module top, so importing ledger
    # here (not at module scope) avoids a circular import.
    from governance_core.candidates import ledger

    out = outbox_dir(project_root)
    # P-0099 (#90 RC2): digests of payloads already staged in the outbox. An
    # unchanged candidate-common skill must NOT be re-minted as a fresh
    # date-stamped envelope every run -- that accumulated same-digest dirs
    # across days and amplified the sweep duplicate-uplink bug (RC1). A
    # changed skill has a new digest and is still staged as an update.
    existing_digests: set[str] = set()
    if out.exists():
        for env_dir in {p.parent for p in out.rglob("candidate.json")}:
            try:
                existing_digests.add(ledger.payload_digest(env_dir))
            except (envelope.EnvelopeError, OSError):
                continue  # a malformed envelope is not a usable dedup key

    built: list[Path] = []
    for skill in sorted(learned.glob("*.md")):
        if read_layer(skill) != "candidate-common":
            continue
        if ledger.skill_digest(skill) in existing_digests:
            continue  # an identical-payload envelope is already staged
        built.append(envelope.build_envelope(
            out,
            kind="skill",
            origin=origin,
            title=skill.stem,
            rationale=(f"net-new learned skill tagged candidate-common: "
                       f"{skill.name}"),
            payload_files=[skill],
            layer="candidate-common",
        ))
    return built
