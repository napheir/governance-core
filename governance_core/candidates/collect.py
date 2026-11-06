"""Candidate collection: outbox location + net-new skill scan (P-0065 Phase 4).

The consumer-side outbox is the pre-uplink staging area for candidate
envelopes -- gitignored, transient. `collect_netnew_skills` is one of the
three candidate sources (the others are drift capture in the installer and
the active `/submit-candidate` flow).

In a business clone of a multi-agent project, core's learned skills arrive
through the master merge. They are core's to offer, not this clone's:
`candidate_skills` leaves out every skill whose content core has committed
(0.49.2, deva-vani).
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from governance_core.candidates import envelope

logger = logging.getLogger("governance_core.candidates.collect")

OUTBOX_REL = ".governance/candidate-outbox"
LEARNED_REL = ".claude/skills/learned"
COLLECT_RATIONALE = "net-new learned skill tagged candidate-common: "


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


def _git(project_root: Path, *args: str, stdin: str | None = None) -> str | None:
    """Return the stdout of `git <args>` in `project_root`, or None on failure."""
    try:
        result = subprocess.run(["git", *args], cwd=project_root, input=stdin,
                                capture_output=True, encoding="utf-8",
                                errors="replace", check=False)
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _business_clone_core_refs(project_root: Path) -> list[str]:
    """Return the core-history refs of a business clone ([] otherwise).

    Empty for the core clone, a single-agent project, an unresolved clone
    identity or an unreadable config -- then nothing counts as core's. The
    refs are config `upstream_branch` then `core_branches` (as check_scope,
    P-0131), keeping those that resolve to a commit here.
    """
    from governance_core import config, installer  # lazy: installer imports collect

    try:
        cfg = config.load_config(project_root)
        guard_common = installer._load_guard_common(project_root)
    except (OSError, KeyError, TypeError, ValueError):
        return []
    if len(cfg.agents) < 2:
        return []
    role = guard_common.detect_role(str(project_root))
    if role in (guard_common.CORE_ROLE, guard_common.UNRESOLVED_ROLE):
        return []
    names = ([cfg.upstream_branch] if cfg.upstream_branch else []) + list(cfg.core_branches)
    refs: list[str] = []
    for ref in names:
        if ref not in refs and _git(project_root, "rev-parse", "-q", "--verify",
                                    f"{ref}^{{commit}}") is not None:
            refs.append(ref)
    return refs


def core_skill_blobs(project_root: Path) -> set[str]:
    """Return the blob ids of every learned-skill version in core history.

    Only for a business clone (see `_business_clone_core_refs`); empty
    otherwise, and on any git failure, so nothing is left out.
    """
    refs = _business_clone_core_refs(project_root)
    if not refs:
        return set()
    out = _git(project_root, "log", "--root", "-m", "--no-renames", "--raw",
               "--no-abbrev", "--format=", *refs, "--", LEARNED_REL + "/")
    if out is None:
        logger.warning("[collect] git log of core history failed in %s; "
                       "core's learned skills are not recognised",
                       project_root)
        return set()
    blobs: set[str] = set()
    for line in out.split("\n"):
        if line.startswith(":"):
            fields = line.split("\t")[0].split()
            if len(fields) >= 4 and fields[3].strip("0"):
                blobs.add(fields[3])
    return blobs


def candidate_skills(project_root: Path) -> list[Path]:
    """Return the learned skills this clone offers as candidates.

    A skill tagged `layer: candidate-common`, unless its content (as git
    would store it, so a CRLF checkout still matches) is a version core has
    committed: in a business clone that skill came in through the master
    merge and is core's to offer.
    """
    learned = project_root / LEARNED_REL
    if not learned.exists():
        return []
    tagged = [skill for skill in sorted(learned.glob("*.md"))
              if read_layer(skill) == "candidate-common"]
    from_core = core_skill_blobs(project_root) if tagged else set()
    if not from_core:
        return tagged
    rels = [skill.relative_to(project_root).as_posix() for skill in tagged]
    out = _git(project_root, "hash-object", "--stdin-paths",
               stdin="\n".join(rels) + "\n")
    blobs = out.split() if out is not None else []
    if len(blobs) != len(tagged):
        logger.warning("[collect] git hash-object failed in %s; core's "
                       "learned skills are not recognised", project_root)
        return tagged
    return [skill for skill, blob in zip(tagged, blobs) if blob not in from_core]


def collected_skill_source(project_root: Path,
                           meta: dict[str, Any]) -> Path | None:
    """Return the learned skill a `collect`-built envelope was packaged from.

    `meta` is a validated candidate.json. Returns None for every other
    envelope (drift capture, /submit-candidate): their payload is not tied
    to one learned skill.
    """
    title = meta["title"]
    if (meta["kind"] != "skill" or "drift_target" in meta
            or meta["rationale"] != f"{COLLECT_RATIONALE}{title}.md"
            or meta["source_paths"] != [f"{envelope.PAYLOAD_DIR}/{title}.md"]):
        return None
    return project_root / LEARNED_REL / f"{title}.md"


def is_withdrawn(project_root: Path, meta: dict[str, Any],
                 offered: set[Path]) -> bool:
    """True if a collected skill envelope's source is no longer offered.

    `offered` is `set(candidate_skills(project_root))`. Relabelling the
    learned skill away from candidate-common, deleting it, or (business
    clone) it being core's merged-in skill withdraws the copy `collect`
    already staged; before 0.49.1 `sweep` uplinked it anyway (deva-vani).
    """
    source = collected_skill_source(project_root, meta)
    return source is not None and source not in offered


def collect_netnew_skills(project_root: Path, origin: str,
                          out_dir: Path | None = None) -> list[Path]:
    """Package every skill `candidate_skills` offers as an envelope.

    Each is built into a `kind: skill` candidate envelope under `out_dir`
    (default: the outbox), unless an identical-payload envelope is already
    staged in the outbox. `sweep --dry-run` passes a scratch `out_dir` so it
    can show what would be sent without writing to the outbox. Returns the
    envelope directories created.
    """
    skills = candidate_skills(project_root)
    if not skills:
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
    for skill in skills:
        if ledger.skill_digest(skill) in existing_digests:
            continue  # an identical-payload envelope is already staged
        built.append(envelope.build_envelope(
            out if out_dir is None else out_dir,
            kind="skill",
            origin=origin,
            title=skill.stem,
            rationale=f"{COLLECT_RATIONALE}{skill.name}",
            payload_files=[skill],
            layer="candidate-common",
        ))
    return built
