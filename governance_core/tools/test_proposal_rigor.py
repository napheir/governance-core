# -*- coding: utf-8 -*-
"""Tests for P-0108 plan-mode rigor grafts on the proposal pipeline.

Covers the net-new code:
  - _v2_scaffold gains `## Current State` + `## Alternatives & Rationale`
  - current_state_adequacy() form-only predicate (the shared gate/audit truth)
  - _extract_section / _extract_scope_file_tokens / _loose_file_match
  - reconcile() coverage lists (git stubbed)
  - audit_proposals Check 13 (WARN-only, grandfather + status/region filters)
  - the 5-dim research paradigm parses in proposal-drafting-checklist.md

Pure functions + temp files; no live proposal corpus or git history required
(reconcile stubs _commit_changed_files / find_by_id).

Run from repo root:
    python tools/test_proposal_rigor.py
    # or: python -m pytest tools/test_proposal_rigor.py -q
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal_lib as pl
import audit_proposals as ap
import proposal_suggest as ps


def out(line: str) -> None:
    sys.stdout.write(line + "\n")


# --- scaffold ---------------------------------------------------------------

def test_scaffold_has_new_sections_in_order():
    body = pl._v2_scaffold("P-0001", "Demo", "core")
    assert body.count("## Current State (read, not assumed)") == 1
    assert body.count("## Alternatives & Rationale") == 1
    # Current State sits between Trigger and Scope
    assert body.index("## Trigger") < body.index("## Current State") < body.index("## Scope")
    # Alternatives sits between Non-Goals and Guardrails
    assert body.index("## Non-Goals") < body.index("## Alternatives & Rationale") < body.index("## Guardrails")


def test_fresh_scaffold_is_inadequate():
    # A freshly created proposal carries only the placeholder -> the research
    # gate must reject it until the author fills it in.
    body = pl._v2_scaffold("P-0001", "Demo", "core")
    ok, _ = pl.current_state_adequacy(body)
    assert not ok


# --- current_state_adequacy truth table -------------------------------------

def test_adequacy_missing_section():
    ok, reason = pl.current_state_adequacy("## Trigger\n\nx\n")
    assert not ok and "missing" in reason


def test_adequacy_placeholder_only():
    body = "## Current State (read, not assumed)\n\n<cite files you read>\n\n## Scope\n"
    ok, _ = pl.current_state_adequacy(body)
    assert not ok


def test_adequacy_prose_without_file_ref():
    body = "## Current State (read, not assumed)\n\nI read the code and it looks fine.\n\n## Scope\n"
    ok, reason = pl.current_state_adequacy(body)
    assert not ok and "concrete file" in reason


def test_adequacy_passes_with_file_dot_ext():
    body = "## Current State (read, not assumed)\n\nRead `tools/proposal_lib.py` — no gate today.\n\n## Scope\n"
    ok, reason = pl.current_state_adequacy(body)
    assert ok and reason == "ok"


def test_adequacy_passes_with_file_line_ref():
    body = "## Current State\n\nsaw foo/bar.py:120 today\n\n## Scope\n"
    ok, _ = pl.current_state_adequacy(body)
    assert ok


def test_adequacy_ignores_fenced_heading():
    # `## Current State` quoted inside a code fence (placeholder) must not be
    # mistaken for the real section that follows the fence with a file ref.
    body = (
        "## Scope\n\nthe scaffold template is:\n\n"
        "```text\n## Current State (read, not assumed)\n<cite files you read>\n```\n\n"
        "## Current State (read, not assumed)\n\nRead `tools/proposal_lib.py:600`.\n\n"
        "## Scope\n"
    )
    ok, reason = pl.current_state_adequacy(body)
    assert ok and reason == "ok"


# --- section extraction primitives ------------------------------------------

def test_extract_section_stops_at_next_h2():
    body = "## A\n\nalpha\n\n## B\n\nbeta\n"
    assert pl._extract_section(body, "## A") == "alpha"
    assert pl._extract_section(body, "## B") == "beta"
    assert pl._extract_section(body, "## C") == ""


def test_extract_section_keeps_h3_inside():
    body = "## Phases\n\n### Phase 1\n\nx\n\n## Risks\n\ny\n"
    sec = pl._extract_section(body, "## Phases")
    assert "### Phase 1" in sec and "x" in sec and "y" not in sec


def test_extract_scope_file_tokens():
    body = ("## Scope\n\nEdit `tools/proposal_lib.py`, audit_proposals.py and "
            "commands/proposal.md:12.\n\n## Non-Goals\n")
    toks = pl._extract_scope_file_tokens(body)
    assert "tools/proposal_lib.py" in toks
    assert "audit_proposals.py" in toks
    assert "commands/proposal.md" in toks       # :12 line suffix dropped
    assert all(":" not in t for t in toks)


def test_loose_file_match():
    assert pl._loose_file_match("proposal_lib.py", "governance_core/tools/proposal_lib.py")
    assert pl._loose_file_match("commands/proposal.md", "governance_core/commands/proposal.md")
    assert not pl._loose_file_match("audit_proposals.py", "governance_core/tools/proposal_lib.py")
    assert not pl._loose_file_match("", "anything")


# --- reconcile (git stubbed) ------------------------------------------------

def test_reconcile_coverage_lists():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "p-9999-x.md"
        p.write_text(
            "---\nid: P-9999\nstatus: approved\n---\n\n"
            "## Scope\n\nEdit `tools/proposal_lib.py`, `commands/proposal.md`, "
            "`tools/orphan.py`.\n\n## Non-Goals\n\nx\n",
            encoding="utf-8",
        )
        orig_find, orig_changed = pl.find_by_id, pl._commit_changed_files
        pl.find_by_id = lambda pid: p
        pl._commit_changed_files = lambda c: [
            "governance_core/tools/proposal_lib.py",
            "governance_core/commands/proposal.md",
            "governance_core/tools/surprise.py",
        ]
        try:
            res = pl.reconcile("P-9999", "deadbeef")
        finally:
            pl.find_by_id, pl._commit_changed_files = orig_find, orig_changed
    # declared in Scope but never changed
    assert "tools/orphan.py" in res["in_scope_not_touched"]
    assert "tools/proposal_lib.py" not in res["in_scope_not_touched"]
    # changed but not declared
    assert "governance_core/tools/surprise.py" in res["touched_not_in_scope"]
    assert "governance_core/tools/proposal_lib.py" not in res["touched_not_in_scope"]


# --- audit Check 13 ---------------------------------------------------------

def _write(d: Path, name: str, status: str, created: str, current_state: str = "") -> Path:
    cs = f"## Current State (read, not assumed)\n\n{current_state}\n\n" if current_state else ""
    p = d / name
    p.write_text(
        f"---\nid: P-{name[2:6]}\nagent: core\nstatus: {status}\ncreated: {created}\n---\n\n"
        f"## Trigger\n\nx\n\n{cs}## Scope\n\ny\n",
        encoding="utf-8",
    )
    return p


def test_check13_warns_post_cutover_inadequate():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        bad = _write(d, "p-9001-bad.md", "pending", "2026-06-22")
        warns = ap._check_current_state_adequacy([bad], d)
    assert len(warns) == 1 and "9001" in warns[0]


def test_check13_grandfathers_pre_cutover():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        old = _write(d, "p-9002-old.md", "pending", "2026-06-01")
        warns = ap._check_current_state_adequacy([old], d)
    assert warns == []


def test_check13_exempts_draft_and_terminal():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        draft = _write(d, "p-9003-dft.md", "draft", "2026-06-22")
        impl = _write(d, "p-9004-imp.md", "implemented", "2026-06-22")
        warns = ap._check_current_state_adequacy([draft, impl], d)
    assert warns == []


def test_check13_passes_adequate():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        good = _write(d, "p-9005-good.md", "approved", "2026-06-22",
                      current_state="Read `tools/proposal_lib.py:600`.")
        warns = ap._check_current_state_adequacy([good], d)
    assert warns == []


# --- research paradigm in the checklist -------------------------------------

def _checklist_path() -> Path:
    """Locate the checklist in either layout: package source uses
    `knowledge_governance/`, the installed autonomy layer uses
    `knowledge/governance/` (gc-test-suite-run-from-autonomy-layer)."""
    base = Path(__file__).resolve().parent.parent
    for rel in ("knowledge_governance/proposal-drafting-checklist.md",
                "knowledge/governance/proposal-drafting-checklist.md"):
        p = base / rel
        if p.is_file():
            return p
    raise FileNotFoundError("proposal-drafting-checklist.md not found in either layout")


def test_checklist_paradigm_parses():
    items = ps.parse_checklist(_checklist_path())
    # 4 original seed entries + 5 paradigm dims, all still parseable
    assert len(items) >= 9
    p0108 = [it for it in items if "P-0108" in (it.get("source") or "")]
    assert len(p0108) == 5


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
