# -*- coding: utf-8 -*-
"""Tests for `related`-by-id (P-0128 Phase A, candidate #139).

Covers the net-new surface:
  - classify_related_ref(): the ONE predicate shared by the writer
    (`proposal_lib link`) and the auditor (Check 18)
  - audit_proposals Check 18: a `P-NNNN` element of `related` must resolve
    in the scanned corpus or the id ledger; self-reference and malformed ids
    fail; free-form refs are untouched; no back-reference is required
  - link_proposal(): fail-fast validation, idempotent append, State Log line,
    target proposal never modified (single-directional)

Temp files only; no live corpus, ledger or git history required.

Run from repo root:
    python -m pytest tools/test_audit_proposals_related.py -q
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import proposal_lib as pl  # noqa: E402
import audit_proposals as ap  # noqa: E402


def _write(d: Path, nnnn: str, related: str = "", status: str = "draft") -> Path:
    """Write a schema-valid proposal; `related` is the raw frontmatter value."""
    rel = f"\nrelated: {related}" if related else ""
    path = d / f"p-{nnnn}-x.md"
    path.write_text(
        f"---\nid: P-{nnnn}\nagent: core\nstatus: {status}\n"
        f"created: 2026-10-09{rel}\nowner: core\n---\n\n"
        f"# Proposal P-{nnnn}: x\n\n## Trigger\n\nx\n\n## State Log\n\n"
        f"- 2026-10-09: draft created by core agent (P-{nnnn})\n",
        encoding="utf-8",
    )
    return path


def _check(tmp_path: Path, monkeypatch, files: list, ledger: set = frozenset()) -> list:
    monkeypatch.setattr(ap, "_ledger_ids", lambda root: set(ledger))
    return ap._check_related_ids(
        {"in-flight": files, "archive": [], "legacy": []}, tmp_path)


# --- shared predicate -------------------------------------------------------

@pytest.mark.parametrize("ref", ["P-0001", "P-0128", "P-12345"])
def test_classify_wellformed_id(ref):
    assert pl.classify_related_ref(ref) == "id"


@pytest.mark.parametrize("ref", ["P-12", "p-0123", "P0123", "P_0123", "P 0123"])
def test_classify_malformed_id(ref):
    assert pl.classify_related_ref(ref) == "malformed-id"


@pytest.mark.parametrize("ref", [
    "../other/p-0001-x.md", "proposals/_archive/2026/p-0114-x.md",
    "knowledge/governance/runtime-import-discipline.md", "EXP-2026-0010"])
def test_classify_freeform_is_other(ref):
    assert pl.classify_related_ref(ref) == "other"


# --- Check 18 ---------------------------------------------------------------

def test_check18_resolving_id_is_clean(tmp_path, monkeypatch):
    a = _write(tmp_path, "0001")
    b = _write(tmp_path, "0002", related="[P-0001]")
    assert _check(tmp_path, monkeypatch, [a, b]) == []


def test_check18_typo_id_fails(tmp_path, monkeypatch):
    a = _write(tmp_path, "0001")
    b = _write(tmp_path, "0002", related="[P-0091]")
    errors = _check(tmp_path, monkeypatch, [a, b])
    assert len(errors) == 1
    assert "Check 18" in errors[0] and "P-0091" in errors[0]
    assert "resolves to no proposal" in errors[0]


def test_check18_ledger_only_id_resolves(tmp_path, monkeypatch):
    # origin lives in another clone: no file here, but the shared ledger has it
    b = _write(tmp_path, "0002", related="[P-0777]")
    assert _check(tmp_path, monkeypatch, [b], ledger={"P-0777"}) == []


def test_check18_single_directional_no_backref_needed(tmp_path, monkeypatch):
    # P-0001 does NOT list P-0002; that must not be an error
    a = _write(tmp_path, "0001")
    b = _write(tmp_path, "0002", related="[P-0001]")
    assert "related" not in a.read_text(encoding="utf-8")
    assert _check(tmp_path, monkeypatch, [a, b]) == []


def test_check18_self_reference_fails(tmp_path, monkeypatch):
    a = _write(tmp_path, "0001", related="[P-0001]")
    errors = _check(tmp_path, monkeypatch, [a])
    assert len(errors) == 1 and "own id" in errors[0]


def test_check18_malformed_id_fails(tmp_path, monkeypatch):
    a = _write(tmp_path, "0001")
    b = _write(tmp_path, "0002", related="[p-0001]")
    errors = _check(tmp_path, monkeypatch, [a, b])
    assert len(errors) == 1 and "looks like a proposal id" in errors[0]


def test_check18_freeform_refs_untouched(tmp_path, monkeypatch):
    b = _write(tmp_path, "0002",
               related="[../gone/p-0999-missing.md, knowledge/x.md]")
    assert _check(tmp_path, monkeypatch, [b]) == []


def test_check18_mixed_list_reports_only_bad_ids(tmp_path, monkeypatch):
    a = _write(tmp_path, "0001")
    b = _write(tmp_path, "0002", related="[P-0001, knowledge/x.md, P-0500]")
    errors = _check(tmp_path, monkeypatch, [a, b])
    assert len(errors) == 1 and "P-0500" in errors[0]


def test_check18_no_related_field_is_clean(tmp_path, monkeypatch):
    assert _check(tmp_path, monkeypatch, [_write(tmp_path, "0001")]) == []


# --- link_proposal (the writer) ---------------------------------------------

@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Two proposals on disk; proposal_lib's discovery pointed at tmp_path."""
    paths = {"P-0001": _write(tmp_path, "0001"),
             "P-0002": _write(tmp_path, "0002")}
    monkeypatch.setattr(pl, "find_by_id", lambda pid: paths[pid] if pid in paths else None)
    monkeypatch.setattr(pl, "_read_ledger", lambda: {
        "version": "1.0.0", "next_id": 800,
        "entries": [{"id": "P-0777"}]})
    monkeypatch.setattr(pl, "_lock_path", lambda: tmp_path / ".lock")
    monkeypatch.setattr(pl, "_lock_timeout", lambda: 5)
    return paths


def test_link_adds_related_and_state_log(repo):
    path, added = pl.link_proposal("P-0002", ["P-0001"])
    fm, body = pl.parse_proposal(path)
    assert added == ["P-0001"] and fm["related"] == ["P-0001"]
    assert "linked related P-0001" in body


def test_link_output_passes_check18(repo, tmp_path, monkeypatch):
    pl.link_proposal("P-0002", ["P-0001", "P-0777"])
    errors = _check(tmp_path, monkeypatch, list(repo.values()), ledger={"P-0777"})
    assert errors == []


def test_link_is_idempotent(repo):
    pl.link_proposal("P-0002", ["P-0001"])
    before = repo["P-0002"].read_text(encoding="utf-8")
    _, added = pl.link_proposal("P-0002", ["P-0001"])
    assert added == [] and repo["P-0002"].read_text(encoding="utf-8") == before


def test_link_does_not_touch_target(repo):
    before = repo["P-0001"].read_text(encoding="utf-8")
    pl.link_proposal("P-0002", ["P-0001"])
    assert repo["P-0001"].read_text(encoding="utf-8") == before


def test_link_accepts_ledger_only_id(repo):
    _, added = pl.link_proposal("P-0002", ["P-0777"])
    assert added == ["P-0777"]


def test_link_keeps_freeform_ref(repo):
    _, added = pl.link_proposal("P-0002", ["knowledge/x.md"])
    assert added == ["knowledge/x.md"]


@pytest.mark.parametrize("ref,needle", [
    ("P-0500", "resolves to no proposal"),
    ("p-0001", "looks like a proposal id"),
    ("P-0002", "own id"),
])
def test_link_rejects_bad_ref_and_writes_nothing(repo, ref, needle):
    before = repo["P-0002"].read_text(encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        pl.link_proposal("P-0002", ["P-0001", ref])
    assert needle in str(exc.value)
    assert repo["P-0002"].read_text(encoding="utf-8") == before


def test_link_unknown_proposal_raises(repo):
    with pytest.raises(FileNotFoundError):
        pl.link_proposal("P-0404", ["P-0001"])
