# -*- coding: utf-8 -*-
"""Tests for the `upstreamed` terminal status (P-0123, issue #136).

Covers the net-new surface:
  - validate_upstreamed_ref() shared grammar predicate (writer + validator
    call the SAME function, so verdict + message never diverge)
  - audit_proposals Check 17: upstreamed_to is format-validated, NOT resolved
    (never stats a local file / seeks a back-reference)
  - Check 6 (local superseded) is UNCHANGED — regression guard
  - enum / terminal-set membership is consistent across the two modules
    (the enum lives in both proposal_lib and audit_proposals — divergence risk)

The three issue acceptance tests map to:
  1. upstreamed + valid ref -> audit clean, no local stat  (test_audit_upstreamed_valid_*)
  2. local superseded_by -> must-exist + back-ref unchanged (test_audit_superseded_*)
  3. malformed external ref -> still FAILs                  (test_audit_upstreamed_malformed)

Pure functions + temp files; no live corpus or git history required.

Run from repo root:
    python tools/test_upstreamed_status.py
    # or: python -m pytest tools/test_upstreamed_status.py -q
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import proposal_lib as pl  # noqa: E402
import audit_proposals as ap  # noqa: E402


def out(line: str) -> None:
    sys.stdout.write(line + "\n")


def _write(d: Path, nnnn: str, status: str, extra_fm: str = "",
           created: str = "2026-07-15") -> Path:
    """Write a fully schema-valid proposal so only the status-conditional
    checks vary (correct id / filename / H1 -> Check 8 stays quiet)."""
    name = f"p-{nnnn}-x.md"
    fm_extra = ("\n" + extra_fm) if extra_fm else ""
    (d / name).write_text(
        f"---\nid: P-{nnnn}\nagent: core\nstatus: {status}\n"
        f"created: {created}{fm_extra}\n---\n\n"
        f"# Proposal P-{nnnn}: x\n\n## Trigger\n\nx\n",
        encoding="utf-8",
    )
    return d / name


def _errors(path: Path, d: Path) -> list:
    return ap._validate_one(path.name, path, d, "archive", True)


# --- shared predicate -------------------------------------------------------

def test_predicate_accepts_repo_path():
    ok, reason = pl.validate_upstreamed_ref(
        "governance-core:proposals/_archive/2026/p-0122-x.md")
    assert ok and reason == ""


def test_predicate_accepts_https_url():
    ok, _ = pl.validate_upstreamed_ref(
        "https://github.com/napheir/governance-core/pull/135")
    assert ok


def test_predicate_accepts_http_url():
    ok, _ = pl.validate_upstreamed_ref("http://example.com/x")
    assert ok


def test_predicate_rejects_bare_path():
    # a bare repo-relative path has no colon + no scheme -> the escape hatch
    # must not launder a typo'd local path (issue test 3)
    ok, reason = pl.validate_upstreamed_ref("proposals/x.md")
    assert not ok
    # message names both accepted forms + a concrete example (owner fixes once)
    assert "<repo-slug>:<path>" in reason and "http" in reason


def test_predicate_rejects_whitespace_and_empty():
    assert not pl.validate_upstreamed_ref("repo:pa th.md")[0]
    assert not pl.validate_upstreamed_ref("")[0]
    assert not pl.validate_upstreamed_ref("governance-core:")[0]  # empty path


# --- Check 17: format-validate, never resolve (issue test 1 + 3) ------------

def test_audit_upstreamed_valid_repo_ref_clean():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9101", "upstreamed",
                   "upstreamed_to: governance-core:proposals/_archive/2026/p-0122-x.md\n"
                   "upstreamed_at: 2026-07-15")
        errs = _errors(p, d)
    assert errs == [], errs


def test_audit_upstreamed_valid_url_clean():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9102", "upstreamed",
                   "upstreamed_to: https://github.com/napheir/governance-core/pull/135\n"
                   "upstreamed_at: 2026-07-15")
        errs = _errors(p, d)
    assert errs == [], errs


def test_audit_upstreamed_never_stats_local_file():
    # the ref looks path-like but lives in another repo: no "non-existent file"
    # (Check 6) error may appear for an upstreamed proposal
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9103", "upstreamed",
                   "upstreamed_to: governance-core:proposals/nope/does_not_exist.md\n"
                   "upstreamed_at: 2026-07-15")
        errs = _errors(p, d)
    assert errs == [], errs
    assert not any("non-existent file" in e for e in errs)


def test_audit_upstreamed_malformed_fails():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9104", "upstreamed",
                   "upstreamed_to: proposals/x.md\n"  # bare path, no colon/scheme
                   "upstreamed_at: 2026-07-15")
        errs = _errors(p, d)
    assert any("Check 17" in e for e in errs), errs
    # malformed ref FAILs on format, NOT on a local-stat attempt
    assert not any("non-existent file" in e for e in errs)


def test_audit_upstreamed_missing_ref_flagged():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9105", "upstreamed", "upstreamed_at: 2026-07-15")
        errs = _errors(p, d)
    # Check 4 (state-conditional required fields) catches the absent ref
    assert any("upstreamed_to" in e for e in errs), errs


# --- Check 6 regression guard (issue test 2) --------------------------------

def test_audit_superseded_missing_target_still_fails():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        p = _write(d, "9106", "superseded",
                   "superseded_by: proposals/does_not_exist.md")
        errs = _errors(p, d)
    # local supersession MUST still enforce must-exist (no regression)
    assert any("non-existent file" in e for e in errs), errs


def test_audit_superseded_local_resolves_and_backrefs():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        (d / "proposals").mkdir()
        # replacement exists AND back-references the superseded file
        (d / "proposals" / "new.md").write_text(
            "---\nid: P-9108\nagent: core\nstatus: pending\ncreated: 2026-07-15\n"
            "supersedes: [p-9107-x.md]\n---\n\n# Proposal P-9108: r\n\nx\n",
            encoding="utf-8",
        )
        p = _write(d, "9107", "superseded", "superseded_by: proposals/new.md")
        errs = _errors(p, d)
    assert errs == [], errs


# --- enum / terminal-set consistency across the two modules -----------------

def test_enum_consistency_across_modules():
    assert "upstreamed" in pl.VALID_STATUS
    assert "upstreamed" in pl.TERMINAL_STATUS
    assert "upstreamed" in ap.VALID_STATUS
    assert ap.REQUIRED_BY_STATUS["upstreamed"] == {"upstreamed_to", "upstreamed_at"}
    # the writer and validator resolve to the SAME predicate object
    assert ap  # module import side-effect guard
    from proposal_lib import validate_upstreamed_ref as writer_pred
    assert writer_pred is pl.validate_upstreamed_ref


def _run() -> int:
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            out(f"[PASS] {fn.__name__}")
        except Exception as exc:  # noqa: BLE001 — test runner reports all
            failed += 1
            out(f"[FAIL] {fn.__name__}: {exc!r}")
    out(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
