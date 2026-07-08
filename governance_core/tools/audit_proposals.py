"""Audit proposals across 3 regions against schema v1.1.0.

Scans (P-0001 Phase 3):
  - In-flight: shared_state/proposals/<agent>/p-NNNN-*.md (single physical
    copy, visible to all clones)
  - Archive: proposals/_archive/<YYYY>/p-NNNN-*.md (terminal proposals,
    git-tracked)
  - Legacy: proposals/*.md top level (pre-v1.1.0 proposals; grandfathered
    per schema §6 — only v1.0.0 checks apply)

Validates:
  Check 1: frontmatter exists (---\nstatus:...\n---) at file start
  Check 2: v1.0.0 required fields (status, created); +v1.1.0 (id, agent)
           for non-legacy files
  Check 3: status enum membership
  Check 4: state-conditional fields (implemented requires implemented_in
           + implemented_at; rejected requires rejection_reason; etc.)
  Check 5: implemented_in is git rev-parse-resolvable
  Check 6: superseded_by points to existing proposal that has matching
           supersedes back-reference
  Check 7: dates are YYYY-MM-DD and chronological (created <= *_at)
  Check 8: three-way id consistency (filename p-NNNN- ↔ frontmatter id ↔
           body H1 `# Proposal P-NNNN:` within first 50 lines)
  Check 9: same P-NNNN MUST NOT exist in both in-flight and archive
           (mutex per Constitution Art.5.1 / schema §5.5)
  Check 10: every P-NNNN in in-flight/archive has an entry in
            shared_state/proposals/_id_ledger.json (P-0057 Phase 3 C1)
  Check 11: same P-NNNN MUST NOT exist in archive of multiple branches
            (cross-branch via `git ls-tree origin/*`) (P-0057 Phase 3 C2)
  Check 12: archive frontmatter `agent` field MUST match the commit author
            (`git log -1 --format=%ae`) — WARN only (P-0057 Phase 3 C3)
  Check 13: in-flight non-terminal proposals created on/after the cutover
            carry an adequate Current State section (shares the transition
            --to approved predicate) — WARN only (P-0108)
  Check 14: in-flight non-terminal COMPLEX proposals created on/after the
            P-0124 cutover carry an adequate Design & Contract section
            (shares the transition --to approved predicate) — WARN only (P-0124)
  Check 15: in-flight non-terminal proposals created on/after the P-0119
            cutover carry SIGNED Approval Criteria (each item has a check
            token; shares the transitional approve predicate) — WARN only (P-0119)

Schema: contracts/proposal_frontmatter_schema.md v1.2.0

Usage:
    python tools/audit_proposals.py            # validate, exit 1 on error
    python tools/audit_proposals.py --root PATH
    python tools/audit_proposals.py --warn-only  # never exit 1 (transition mode)

Exit codes:
    0 = all proposals pass
    1 = at least one failure
"""
import argparse
import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path


VALID_STATUS = {
    "draft", "pending", "approved", "in-progress",
    "implemented", "superseded", "rejected",
}

VALID_AGENTS = {"core", "rules", "trade", "data", "research"}

# State -> required additional fields
REQUIRED_BY_STATUS = {
    "draft": set(),
    "pending": set(),
    "approved": {"approved_at"},
    "in-progress": {"started_at"},
    "implemented": {"implemented_in", "implemented_at"},
    "superseded": {"superseded_by"},
    "rejected": {"rejected_at", "rejection_reason"},
}

# Check 13 (P-0108): in-flight non-terminal proposals created on/after this
# cutover must carry an adequate Current State section. Pre-cutover proposals
# are grandfathered so the 135 pre-G1 proposals don't flood the audit.
CURRENT_STATE_CUTOVER = "2026-06-22"
_CURRENT_STATE_CHECKED_STATUSES = {"pending", "approved", "in-progress"}

# Check 14 (P-0124): the Design & Contract section only exists in the scaffold
# as of P-0124, so grandfather everything created before its landing date —
# older complex proposals never had the section and would flood the audit.
DESIGN_CONTRACT_CUTOVER = "2026-06-23"

# Check 15 (P-0119): the signed check-token grammar for Approval Criteria did
# not exist before this cutover — grandfather everything older.
APPROVAL_CRITERIA_CUTOVER = "2026-07-08"

_FRONTMATTER_OPEN = re.compile(r"\A---\s*\n")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")
_ID_RE = re.compile(r"^P-(\d{4,})$")
_FILENAME_ID_RE = re.compile(r"^p-(\d{4,})-")
_BODY_TITLE_RE = re.compile(r"^#\s+Proposal\s+(P-\d{4,}):", re.MULTILINE)


def _parse_frontmatter(text: str) -> tuple:
    """Return (frontmatter_dict, error_or_none)."""
    if not _FRONTMATTER_OPEN.match(text):
        return None, "no frontmatter (file must start with '---')"
    end = text.find("\n---\n", 4)
    if end < 0:
        return None, "frontmatter not closed (missing standalone '---' line)"
    body = text[4:end]
    fm = {}
    for line in body.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        if val.startswith("'") and val.endswith("'"):
            val = val[1:-1]
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [x.strip().strip("'\"") for x in inner.split(",") if x.strip()]
            fm[key] = items
        else:
            fm[key] = val
    return fm, None


def _git_hash_resolves(h: str, repo_root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", h],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5, cwd=str(repo_root),
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _is_new_scheme(filename: str) -> bool:
    """True iff filename matches p-NNNN- prefix (v1.1.0 new ID scheme)."""
    return bool(_FILENAME_ID_RE.match(filename))


def _validate_one(rel_path: str, full_path: Path, repo_root: Path,
                  region: str, is_new_scheme: bool) -> list:
    """Validate one proposal file. Returns list of error strings (empty = ok).

    Args:
        rel_path: path relative to repo_root (or shared_state parent) for messages
        full_path: absolute Path
        repo_root: agent-core repo root (for git rev-parse + superseded_by resolve)
        region: 'in-flight' | 'archive' | 'legacy' (for error context)
        is_new_scheme: True if filename has p-NNNN- prefix (v1.1.0 rules apply)
    """
    errors = []
    try:
        text = full_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"cannot read: {exc}"]

    fm, err = _parse_frontmatter(text)
    if err:
        return [err]

    # Check 2: required fields (v1.0.0 always; v1.1.0 only for new-scheme)
    base_required = ("status", "created")
    for f in base_required:
        if f not in fm:
            errors.append(f"missing required field: {f}")
    if is_new_scheme:
        for f in ("id", "agent"):
            if f not in fm:
                errors.append(f"missing v1.1.0 required field: {f}")
    if any("missing required field: status" in e for e in errors):
        return errors

    status = fm["status"]
    # Check 3: enum
    if status not in VALID_STATUS:
        errors.append(f"status '{status}' not in enum {sorted(VALID_STATUS)}")
        return errors

    # v1.1.0: agent enum
    if is_new_scheme and "agent" in fm:
        if fm["agent"] not in VALID_AGENTS:
            errors.append(
                f"agent '{fm['agent']}' not in enum {sorted(VALID_AGENTS)}"
            )

    # Check 4: state-conditional fields
    needed = REQUIRED_BY_STATUS.get(status, set())
    missing = needed - set(fm.keys())
    if missing:
        errors.append(f"status={status} requires fields: {sorted(missing)}")

    # Check 5: hash resolves
    if status == "implemented" and "implemented_in" in fm:
        h = fm["implemented_in"]
        if not _HASH_RE.match(h):
            errors.append(f"implemented_in '{h}' not a hex hash")
        elif not _git_hash_resolves(h, repo_root):
            errors.append(f"implemented_in '{h}' does not git rev-parse")

    # Check 6: superseded_by bidirectional
    if status == "superseded" and "superseded_by" in fm:
        target_rel = fm["superseded_by"]
        target = repo_root / target_rel
        if not target.is_file():
            errors.append(
                f"superseded_by '{target_rel}' points to non-existent file"
            )
        else:
            try:
                t_text = target.read_text(encoding="utf-8")
            except OSError:
                errors.append(f"cannot read superseded_by target: {target_rel}")
            else:
                t_fm, _ = _parse_frontmatter(t_text)
                if t_fm:
                    supersedes = t_fm.get("supersedes", [])
                    if isinstance(supersedes, str):
                        supersedes = [supersedes]
                    if rel_path not in supersedes:
                        errors.append(
                            f"superseded_by '{target_rel}' lacks back-reference "
                            f"in its 'supersedes' list"
                        )

    # Check 7: date format + ordering
    date_fields = ("created", "approved_at", "started_at", "implemented_at",
                   "rejected_at")
    dates = {}
    for f in date_fields:
        if f in fm:
            v = fm[f]
            if not _DATE_RE.match(v):
                errors.append(f"{f} '{v}' not ISO YYYY-MM-DD")
            else:
                try:
                    dates[f] = _dt.date.fromisoformat(v)
                except ValueError:
                    errors.append(f"{f} '{v}' invalid date")

    if "created" in dates:
        for f, d in dates.items():
            if f != "created" and d < dates["created"]:
                errors.append(f"{f} {d} earlier than created {dates['created']}")

    # Check 8: three-way id consistency (v1.1.0 only)
    if is_new_scheme:
        errors.extend(_check_three_way_id(full_path.name, fm, text))

    return errors


def _check_three_way_id(filename: str, fm: dict, text: str) -> list:
    """Check 8: filename `p-NNNN-` ↔ frontmatter id `P-NNNN` ↔ body H1.

    Body H1 must appear within first 50 lines (search heuristic).
    """
    errors = []
    file_m = _FILENAME_ID_RE.match(filename)
    file_nnnn = file_m.group(1) if file_m else None

    fm_id = fm.get("id", "")
    fm_m = _ID_RE.match(fm_id)
    fm_nnnn = fm_m.group(1) if fm_m else None

    # Body H1 within first 50 lines after frontmatter
    end = text.find("\n---\n", 4)
    body = text[end + 5:] if end >= 0 else ""
    body_head = "\n".join(body.splitlines()[:50])
    body_m = _BODY_TITLE_RE.search(body_head)
    body_id = body_m.group(1) if body_m else None
    body_nnnn = body_id.split("-")[1] if body_id else None

    if not file_nnnn:
        errors.append(f"Check 8: filename '{filename}' lacks p-NNNN- prefix")
    if not fm_nnnn:
        errors.append(f"Check 8: frontmatter id '{fm_id!r}' not P-NNNN format")
    if not body_nnnn:
        errors.append("Check 8: body H1 lacks `# Proposal P-NNNN:` within first 50 lines")

    nnnns = [n for n in (file_nnnn, fm_nnnn, body_nnnn) if n]
    if len(set(nnnns)) > 1:
        errors.append(
            f"Check 8: id mismatch — filename={file_nnnn} "
            f"frontmatter={fm_nnnn} body={body_nnnn}"
        )
    return errors


def _check_mutex_in_flight_archive(in_flight: list, archive: list) -> list:
    """Check 9: same NNNN MUST NOT appear in both in-flight and archive."""
    errors = []
    in_flight_ids = {}  # nnnn -> path
    for p in in_flight:
        m = _FILENAME_ID_RE.match(p.name)
        if m:
            in_flight_ids[m.group(1)] = p
    for p in archive:
        m = _FILENAME_ID_RE.match(p.name)
        if m and m.group(1) in in_flight_ids:
            errors.append(
                f"Check 9 MUTEX: P-{m.group(1)} exists in BOTH "
                f"in-flight {in_flight_ids[m.group(1)]} AND archive {p}"
            )
    return errors


def _check_ledger_completeness(in_flight: list, archive: list, repo_root: Path) -> list:
    """Check 10 (P-0057 Phase 3 C1): every NNNN in fs has ledger entry.

    Bootstraps gracefully — if ledger absent, returns advisory error
    pointing to `proposal_lib.py migrate-ledger`.
    """
    import json as _json
    from governance_core.config import load_proposals_config
    errors = []
    # P-0070 Fix A: resolve the ledger from .governance/config.json's
    # shared_state_root (the source proposal_lib.py uses) -- not a hardcoded
    # parent-relative path, which is wrong for a self-hosted layout.
    ledger_path = Path(load_proposals_config(repo_root)["id_ledger_path"])
    if not ledger_path.exists():
        errors.append(
            f"Check 10 LEDGER: {ledger_path} does not exist — "
            "run `python tools/proposal_lib.py migrate-ledger` to bootstrap"
        )
        return errors
    try:
        ledger = _json.loads(ledger_path.read_text(encoding="utf-8"))
        ledger_ids = {e["id"] for e in ledger.get("entries", []) if isinstance(e, dict)}
    except Exception as e:
        errors.append(f"Check 10 LEDGER: failed to parse {ledger_path}: {e}")
        return errors
    fs_ids = set()
    for p in list(in_flight) + list(archive):
        m = _FILENAME_ID_RE.match(p.name)
        if m:
            fs_ids.add(f"P-{int(m.group(1)):04d}")
    missing = fs_ids - ledger_ids
    for pid in sorted(missing):
        errors.append(
            f"Check 10 LEDGER: {pid} present on filesystem but absent from "
            f"_id_ledger.json — rerun migrate-ledger"
        )
    return errors


def _git_list_feature_branches() -> list[str]:
    """List origin/feature/<*> branches (feature branches only, exclude master)."""
    try:
        result = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin/feature"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        return [
            b.strip() for b in result.stdout.splitlines()
            if b.strip().startswith("origin/feature/")
        ]
    except Exception:
        return []


def _git_ls_archive(branch: str) -> list[str]:
    """List proposals/_archive/*/p-NNNN-*.md files on `branch`."""
    try:
        result = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", branch, "proposals/_archive/"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return []
        return [
            f for f in result.stdout.splitlines()
            if _FILENAME_ID_RE.match(Path(f).name or "")
        ]
    except Exception:
        return []


def _check_cross_branch_archive_collision(repo_root: Path) -> list:
    """Check 11 (P-0057 Phase 3 C2): archive on feature branch must also
    be on master (i.e., feature branch must not be the SoT for any archive).

    Detection rule (corrected from naive "exists on multiple branches"
    which trivially fires for feature branches that contain master
    history): for each feature branch, compute `archive_set(feature) -
    archive_set(master)`. Non-empty diff means the feature branch has
    proposals archived only on itself — exactly the P-0056 dogfood
    pattern that triggered P-0057.
    """
    errors = []
    feature_branches = _git_list_feature_branches()
    if not feature_branches:
        return errors  # offline / no remotes — skip

    def _ids_for(branch: str) -> set[str]:
        ids: set[str] = set()
        for path in _git_ls_archive(branch):
            m = _FILENAME_ID_RE.match(Path(path).name)
            if m:
                ids.add(f"P-{int(m.group(1)):04d}")
        return ids

    master_ids = _ids_for("origin/master")
    for branch in feature_branches:
        feat_ids = _ids_for(branch)
        only_on_feature = feat_ids - master_ids
        for pid in sorted(only_on_feature):
            errors.append(
                f"Check 11 X-BRANCH: {pid} archived on {branch} but NOT on "
                f"origin/master — Art.5.1 requires master as canonical archive "
                f"SoT (feature branch self-archive must merge into master)"
            )
    return errors


def _check_archive_author_match(archive: list, repo_root: Path) -> list:
    """Check 12 (P-0057 Phase 3 C3): WARN-only — archive frontmatter
    `agent` should match the email-prefix of the commit author for that file.

    Heuristic only — accepted mismatches: core archiving for another agent,
    historical migrations. Reports as WARN, never blocks.
    """
    warnings = []
    for path in archive:
        try:
            text = path.read_text(encoding="utf-8")
            fm, err = _parse_frontmatter(text)
            if err or not isinstance(fm, dict):
                continue
            owner = fm.get("agent")
            if not owner:
                continue
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ae", "--", str(path)],
                capture_output=True, text=True, timeout=10, cwd=repo_root,
            )
            if result.returncode != 0:
                continue
            author_email = result.stdout.strip()
            if not author_email:
                continue
            # Heuristic: derive likely agent from email prefix or sender role
            author_prefix = author_email.split("@")[0].lower()
            if owner.lower() not in author_prefix and author_prefix not in owner.lower():
                # Tolerate core archiving other agents' proposals (legacy)
                if author_prefix in {"napheir", "core"}:
                    continue
                warnings.append(
                    f"Check 12 WARN: {path.name} owner={owner!r} but commit "
                    f"author={author_email!r} (heuristic mismatch — verify "
                    f"intentional cross-owner archive)"
                )
        except Exception:
            continue
    return warnings


def _check_current_state_adequacy(in_flight: list, repo_root: Path) -> list:
    """Check 13 (P-0108): WARN-only — in-flight non-terminal proposals created
    on/after CURRENT_STATE_CUTOVER must have an adequate Current State section.

    Shares the `current_state_adequacy` predicate with the `transition --to
    approved` BLOCK so WARN and BLOCK never disagree. Archive + legacy + draft
    + pre-cutover proposals are exempt (grandfathered) so the 135 pre-G1
    proposals don't flood the audit. Fails open (no WARN) if the predicate
    can't be imported -- this is an advisory check, never a hard gate here.
    """
    warnings = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from proposal_lib import current_state_adequacy, parse_proposal
    except Exception:
        return warnings  # predicate unavailable -> fail open (WARN-only check)
    for path in in_flight:
        try:
            fm, body = parse_proposal(path)
        except Exception:
            continue
        if fm.get("status") not in _CURRENT_STATE_CHECKED_STATUSES:
            continue
        created = fm.get("created", "")
        if not _DATE_RE.match(created) or created < CURRENT_STATE_CUTOVER:
            continue  # pre-cutover grandfathered
        ok, reason = current_state_adequacy(body)
        if not ok:
            warnings.append(
                f"Check 13 WARN: {path.name} ({fm.get('status')}) "
                f"Current State inadequate — {reason}"
            )
    return warnings


def _check_design_contract_adequacy(in_flight: list, repo_root: Path) -> list:
    """Check 14 (P-0124): WARN-only — in-flight non-terminal COMPLEX proposals
    created on/after DESIGN_CONTRACT_CUTOVER must have an adequate Design &
    Contract section.

    Shares BOTH predicates (`design_contract_adequacy` + `_is_complex_proposal`)
    with the `transition --to approved` BLOCK so WARN and BLOCK never disagree.
    Simple proposals, archive + legacy + draft + terminal + pre-cutover are
    exempt. Fails open (no WARN) if the predicate can't be imported -- advisory
    check, never a hard gate here.
    """
    warnings = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from proposal_lib import (
            design_contract_adequacy, _is_complex_proposal, parse_proposal,
        )
    except Exception:
        return warnings  # predicate unavailable -> fail open (WARN-only check)
    for path in in_flight:
        try:
            fm, body = parse_proposal(path)
        except Exception:
            continue
        if fm.get("status") not in _CURRENT_STATE_CHECKED_STATUSES:
            continue
        created = fm.get("created", "")
        if not _DATE_RE.match(created) or created < DESIGN_CONTRACT_CUTOVER:
            continue  # pre-cutover grandfathered
        if not _is_complex_proposal(body):
            continue  # simple proposals are exempt (gate doesn't fire either)
        ok, reason = design_contract_adequacy(body)
        if not ok:
            warnings.append(
                f"Check 14 WARN: {path.name} ({fm.get('status')}) "
                f"Design & Contract inadequate — {reason}"
            )
    return warnings


def _check_approval_criteria_adequacy(in_flight: list, repo_root: Path) -> list:
    """Check 15 (P-0119): WARN-only — in-flight non-terminal proposals created
    on/after APPROVAL_CRITERIA_CUTOVER whose Approval Criteria items lack a
    check token (cmd:/agent-rubric:/human-verify:).

    Shares the `approval_criteria_adequacy` predicate with the transitional
    `transition --to approved` WARN so the two never disagree. Archive + legacy
    + draft + terminal + pre-cutover are exempt (the check-token grammar did not
    exist before). Fails open (no WARN) if the predicate can't be imported.
    """
    warnings = []
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from proposal_lib import approval_criteria_adequacy, parse_proposal
    except Exception:
        return warnings  # predicate unavailable -> fail open (WARN-only check)
    for path in in_flight:
        try:
            fm, body = parse_proposal(path)
        except Exception:
            continue
        if fm.get("status") not in _CURRENT_STATE_CHECKED_STATUSES:
            continue
        created = fm.get("created", "")
        if not _DATE_RE.match(created) or created < APPROVAL_CRITERIA_CUTOVER:
            continue  # pre-cutover grandfathered
        ok, reason = approval_criteria_adequacy(body)
        if not ok:
            warnings.append(
                f"Check 15 WARN: {path.name} ({fm.get('status')}) "
                f"Approval Criteria unsigned — {reason}"
            )
    return warnings


def _collect_files(repo_root: Path) -> dict:
    """Return {region: [path, ...]} for the 3 scan regions.

    - in-flight: <shared_state_root>/proposals/<agent>/p-*.md
                 (shared_state_root from .governance/config.json -- P-0070)
    - archive:   <repo_root>/proposals/_archive/<YYYY>/p-*.md
    - legacy:    <repo_root>/proposals/*.md (top level, excluding _archive,
                 templates, and `_*.md` discussion artifacts)
    """
    from governance_core.config import load_proposals_config
    out = {"in-flight": [], "archive": [], "legacy": []}

    # P-0070 Fix A: in-flight proposals live under the configured
    # shared_state_root, not a hardcoded parent-relative path.
    shared_state_root = Path(
        load_proposals_config(repo_root)["shared_state_proposals_dir"])
    if shared_state_root.is_dir():
        for sub in sorted(shared_state_root.iterdir()):
            if not sub.is_dir():
                continue
            for p in sorted(sub.glob("*.md")):
                if p.name == "README.md":
                    continue
                out["in-flight"].append(p)

    archive_root = repo_root / "proposals" / "_archive"
    if archive_root.is_dir():
        for p in sorted(archive_root.rglob("*.md")):
            out["archive"].append(p)

    legacy_root = repo_root / "proposals"
    if legacy_root.is_dir():
        for p in sorted(legacy_root.glob("*.md")):
            if not p.is_file():
                continue
            if p.name.startswith("_"):  # _review_*.md / _handoff_*.md / etc
                continue
            out["legacy"].append(p)
        # templates exclusion at deeper level
        for p in sorted((legacy_root).rglob("*.md")):
            parts = p.relative_to(legacy_root).parts
            if parts and parts[0] == "templates":
                continue
            # _archive already collected separately

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--warn-only", action="store_true",
                        help="report errors but exit 0 (transition mode)")
    args = parser.parse_args()

    repo_root = args.root.resolve()
    if not (repo_root / "proposals").is_dir():
        sys.stderr.write(f"[ERROR] {repo_root}/proposals not found\n")
        return 1

    regions = _collect_files(repo_root)
    total = sum(len(v) for v in regions.values())
    if total == 0:
        sys.stdout.write("[INFO] no proposals found in any region\n")
        return 0

    sys.stdout.write(
        f"[SCAN] in-flight={len(regions['in-flight'])} "
        f"archive={len(regions['archive'])} "
        f"legacy={len(regions['legacy'])}\n\n"
    )

    fail_count = 0

    # Per-file checks
    for region, files in regions.items():
        for full in files:
            try:
                rel = full.relative_to(repo_root).as_posix()
            except ValueError:
                # in-flight files live outside repo_root
                rel = str(full)
            is_new = _is_new_scheme(full.name) or region == "in-flight"
            errors = _validate_one(rel, full, repo_root, region, is_new)
            if errors:
                fail_count += 1
                sys.stdout.write(f"FAIL [{region}]: {rel}\n")
                for e in errors:
                    sys.stdout.write(f"  - {e}\n")

    # Cross-region Check 9
    mutex_errors = _check_mutex_in_flight_archive(
        regions["in-flight"], regions["archive"]
    )
    for e in mutex_errors:
        fail_count += 1
        sys.stdout.write(f"FAIL [mutex]: {e}\n")

    # Check 10: ledger completeness (P-0057 Phase 3 C1)
    ledger_errors = _check_ledger_completeness(
        regions["in-flight"], regions["archive"], repo_root
    )
    for e in ledger_errors:
        fail_count += 1
        sys.stdout.write(f"FAIL [ledger]: {e}\n")

    # Check 11: cross-branch archive collision (P-0057 Phase 3 C2)
    x_branch_errors = _check_cross_branch_archive_collision(repo_root)
    for e in x_branch_errors:
        fail_count += 1
        sys.stdout.write(f"FAIL [x-branch]: {e}\n")

    # Check 12: archive author heuristic (WARN only, P-0057 Phase 3 C3)
    warnings = _check_archive_author_match(regions["archive"], repo_root)
    # Check 13: Current State adequacy (WARN only, P-0108) — shares the
    # transition --to approved predicate; grandfathers pre-cutover proposals.
    warnings += _check_current_state_adequacy(regions["in-flight"], repo_root)
    # Check 14: Design & Contract adequacy (WARN only, P-0124) — shares the
    # transition --to approved predicate; complex + post-cutover only.
    warnings += _check_design_contract_adequacy(regions["in-flight"], repo_root)
    # Check 15: Approval Criteria signed (WARN only, P-0119) — shares the
    # transitional approve predicate; post-cutover only.
    warnings += _check_approval_criteria_adequacy(regions["in-flight"], repo_root)
    for w in warnings:
        sys.stdout.write(f"WARN: {w}\n")

    sys.stdout.write(
        f"\n[{fail_count}/{total} failures, {len(warnings)} warnings] "
        f"audited {total} proposals across 3 regions\n"
    )

    if fail_count > 0 and not args.warn_only:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
