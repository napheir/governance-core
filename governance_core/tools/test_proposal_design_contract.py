# -*- coding: utf-8 -*-
"""Tests for P-0124 Design & Contract spec section + conditional approve gate.

Covers the net-new code on top of the P-0108 rigor grafts:
  - _v2_scaffold gains `## Design & Contract` (+ 3 H3 sub-parts) and
    `## Open Questions`; `## Approval Criteria` becomes a checklist
  - design_contract_adequacy() form-only predicate (shared gate/audit truth)
  - _is_complex_proposal() structural trigger (>=2 real phases OR contracts/ scope)
  - transition_proposal --to approved BLOCK for complex proposals + the
    --allow-thin-spec escape hatch
  - audit_proposals Check 14 (WARN-only) agrees with the approve gate
  - create auto-emits the proposal_suggest ①②③ recall

Pure functions + temp files; the approve-gate tests stub the config-derived
seams (find_by_id / _lock_path / _lock_timeout / _write_snapshot) so no live
proposal corpus, config.json, or git history is required.

Run from repo root:
    python tools/test_proposal_design_contract.py
    # or: python -m pytest tools/test_proposal_design_contract.py -q
"""
import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal_lib as pl
import audit_proposals as ap
import proposal_suggest as ps  # noqa: F401  (ensures module is importable/cached)


def out(line: str) -> None:
    sys.stdout.write(line + "\n")


# --- fixtures ---------------------------------------------------------------

_ADEQUATE_CS = "Read `tools/proposal_lib.py:765` today; no design gate yet."

_FILLED_DESIGN = (
    "### Interfaces, I/O & Realization\n"
    "`foo(x: int) -> str` reads config.json field `a`, writes out.txt; the CLI\n"
    "performs it end-to-end.\n\n"
    "### Field Dictionary\n\n"
    "| field | type | meaning | producer | consumer | constraints / allowed values |\n"
    "|-------|------|---------|----------|----------|------------------------------|\n"
    "| a | int | the thing | foo | bar | >=0 (contracts/x.md) |\n\n"
    "### Flow\n"
    "config.json -> foo -> out.txt\n"
)

_PLACEHOLDER_DESIGN = (
    "### Interfaces, I/O & Realization\n"
    "<Each new/changed boundary: signature, INPUT, OUTPUT, realizer.>\n\n"
    "### Field Dictionary\n"
    "<Every field that flows across a boundary.>\n\n"
    "| field | type | meaning | producer | consumer | constraints / allowed values |\n"
    "|-------|------|---------|----------|----------|------------------------------|\n\n"
    "### Flow\n"
    "<producer -> transform -> consumer -> sink.>\n"
)


def _proposal(*, current_state=_ADEQUATE_CS, design=_PLACEHOLDER_DESIGN,
              phases=1, scope="adjust a local helper", status="pending",
              pid="P-9100", created="2026-06-23") -> str:
    """Build a proposal body string with a controllable Design & Contract /
    Phase / Scope shape. Current State is adequate by default so the P-0108
    gate passes and the P-0124 gate is what's under test."""
    if phases >= 2:
        phase_block = ("### Phase 0: Governance bootstrap\n\n- x\n\n"
                       "### Phase 1: Implement the thing\n\n- y\n")
    elif phases == 1:
        phase_block = "### Phase 1: Implement the thing\n\n- y\n"
    else:
        phase_block = ""
    nnnn = pid.split("-")[1]
    return (
        f"---\nid: {pid}\nagent: core\nstatus: {status}\ncreated: {created}\n---\n\n"
        f"# Proposal {pid}: Fixture\n\n"
        f"## Trigger\n\nx\n\n"
        f"## Current State (read, not assumed)\n\n{current_state}\n\n"
        f"## Scope\n\n{scope}\n\n"
        f"## Design & Contract\n\n> Proportionate.\n\n{design}\n"
        f"## Non-Goals\n\nnone\n\n"
        f"## Open Questions\n\nNone\n\n"
        f"## Phases\n\n{phase_block}\n"
        f"## Approval Criteria\n\n- [ ] x\n"
    )


@contextlib.contextmanager
def _approve_seams(path: Path):
    """Stub the config-derived seams so transition_proposal runs against a lone
    temp file with no config.json / corpus / snapshot dir."""
    orig = {k: getattr(pl, k) for k in
            ("find_by_id", "_lock_path", "_lock_timeout", "_write_snapshot")}
    pl.find_by_id = lambda pid: path
    pl._lock_path = lambda: path.parent / ".proposal.lock"
    pl._lock_timeout = lambda: 5
    pl._write_snapshot = lambda *a, **k: None
    try:
        yield
    finally:
        for k, v in orig.items():
            setattr(pl, k, v)


def _approve(body: str, *, allow_thin_spec: bool = False) -> tuple:
    """Write `body` to a temp pending proposal and run --to approved. Returns
    (path, prev, new) on success; raises ValueError if a gate blocks."""
    with tempfile.TemporaryDirectory() as dd:
        p = Path(dd) / "p-9100-fixture.md"
        p.write_text(body, encoding="utf-8")
        with _approve_seams(p):
            return pl.transition_proposal(
                "P-9100", "approved", note="user said 同意",
                allow_thin_spec=allow_thin_spec,
            )


# --- scaffold ---------------------------------------------------------------

def test_scaffold_has_design_and_open_questions():
    body = pl._v2_scaffold("P-0001", "Demo", "core")
    assert body.count("## Design & Contract") == 1
    assert body.count("## Open Questions") == 1
    for sub in pl._DESIGN_CONTRACT_SUBHEADINGS:
        assert sub in body
    # Design & Contract sits between Scope and Non-Goals
    assert body.index("## Scope") < body.index("## Design & Contract") < body.index("## Non-Goals")
    # Open Questions sits between Non-Goals and Alternatives & Rationale
    assert body.index("## Non-Goals") < body.index("## Open Questions") < body.index("## Alternatives & Rationale")
    # Approval Criteria is now a checklist
    crit = pl._extract_section(body, "## Approval Criteria")
    assert "- [ ]" in crit


def test_fresh_scaffold_not_complex():
    # A freshly created scaffold has only placeholder phases and an empty scope,
    # so it must NOT be treated as complex (else every create would gate).
    body = pl._v2_scaffold("P-0001", "Demo", "core")
    assert pl._is_complex_proposal(body) is False


# --- design_contract_adequacy truth table -----------------------------------

def test_design_adequacy_missing_section():
    ok, reason = pl.design_contract_adequacy("## Trigger\n\nx\n")
    assert not ok and "missing '## Design & Contract'" in reason


def test_design_adequacy_placeholder_blocked():
    body = _proposal(design=_PLACEHOLDER_DESIGN)
    ok, reason = pl.design_contract_adequacy(body)
    assert not ok and "Interfaces" in reason


def test_design_adequacy_filled_ok():
    body = _proposal(design=_FILLED_DESIGN)
    ok, reason = pl.design_contract_adequacy(body)
    assert ok and reason == "ok"


def test_design_adequacy_na_escape():
    # Each sub-part may be an explicit N/A line instead of real content.
    na_design = (
        "### Interfaces, I/O & Realization\n"
        "N/A — pure docs change, no boundary touched.\n\n"
        "### Field Dictionary\n"
        "N/A — no field crosses a boundary.\n\n"
        "### Flow\n"
        "N/A — no data flow.\n"
    )
    body = _proposal(design=na_design)
    ok, reason = pl.design_contract_adequacy(body)
    assert ok and reason == "ok"


def test_design_adequacy_empty_field_dict_table_is_unfilled():
    # A bare Field-Dictionary skeleton (header + rule, no data row, no N/A) must
    # NOT count as filled even though the other two sub-parts have prose.
    design = (
        "### Interfaces, I/O & Realization\n"
        "real prose about the CLI realizer.\n\n"
        "### Field Dictionary\n\n"
        "| field | type | meaning | producer | consumer | constraints / allowed values |\n"
        "|-------|------|---------|----------|----------|------------------------------|\n\n"
        "### Flow\n"
        "a -> b\n"
    )
    ok, reason = pl.design_contract_adequacy(_proposal(design=design))
    assert not ok and "Field Dictionary" in reason


# --- _is_complex_proposal ---------------------------------------------------

def test_is_complex_two_phases():
    assert pl._is_complex_proposal(_proposal(phases=2)) is True


def test_is_complex_one_phase_simple_false():
    assert pl._is_complex_proposal(_proposal(phases=1, scope="local helper")) is False


def test_is_complex_contracts_scope():
    body = _proposal(phases=1, scope="Edit `contracts/proposal_frontmatter_schema.md`.")
    assert pl._is_complex_proposal(body) is True


def test_count_real_phases_ignores_placeholders():
    body = ("## Phases\n\n### Phase 0: <Governance bootstrap, when applicable>\n\n"
            "### Phase 1: <Next phase>\n\n## Risks\n")
    assert pl._count_real_phases(body) == 0


# --- approve gate behavior (a)-(d) ------------------------------------------

def test_simple_proposal_with_empty_design_approves():  # (a)
    # 0-1 phase, no contracts/ scope, placeholder Design & Contract -> not
    # complex -> design gate skipped -> approve succeeds (Current State ok).
    _, prev, new = _approve(_proposal(phases=1, design=_PLACEHOLDER_DESIGN))
    assert (prev, new) == ("pending", "approved")


def test_complex_placeholder_design_blocked():  # (b)
    try:
        _approve(_proposal(phases=2, design=_PLACEHOLDER_DESIGN))
    except ValueError as e:
        assert "design-contract gate" in str(e)
    else:
        raise AssertionError("expected the design-contract gate to BLOCK approve")


def test_complex_filled_design_approves():  # (c)
    _, prev, new = _approve(_proposal(phases=2, design=_FILLED_DESIGN))
    assert (prev, new) == ("pending", "approved")


def test_allow_thin_spec_escape():  # (d)
    _, prev, new = _approve(_proposal(phases=2, design=_PLACEHOLDER_DESIGN),
                            allow_thin_spec=True)
    assert (prev, new) == ("pending", "approved")


def test_current_state_gate_still_fires_before_design():
    # The P-0108 Current State gate must not be weakened: a complex proposal
    # with an inadequate Current State is blocked on THAT gate first.
    body = _proposal(phases=2, design=_FILLED_DESIGN,
                     current_state="<cite files you read>")
    try:
        _approve(body)
    except ValueError as e:
        assert "research gate" in str(e)
    else:
        raise AssertionError("expected the Current State research gate to BLOCK")


# --- audit Check 14 agrees with the gate (e) --------------------------------

def _write_inflight(d: Path, name: str, body: str) -> Path:
    p = d / name
    p.write_text(body, encoding="utf-8")
    return p


def test_audit_check14_agrees_with_gate():  # (e)
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        bad_body = _proposal(phases=2, design=_PLACEHOLDER_DESIGN)
        good_body = _proposal(phases=2, design=_FILLED_DESIGN)
        bad = _write_inflight(d, "p-9100-bad.md", bad_body)
        good = _write_inflight(d, "p-9101-good.md", good_body)
        warns = ap._check_design_contract_adequacy([bad, good], d)
    # audit WARNs exactly the inadequate one
    assert len(warns) == 1 and "9100" in warns[0]
    # ...and the shared predicate agrees with that verdict for both bodies
    assert pl._is_complex_proposal(bad_body) and not pl.design_contract_adequacy(bad_body)[0]
    assert pl._is_complex_proposal(good_body) and pl.design_contract_adequacy(good_body)[0]


def test_audit_check14_exempts_simple_and_pre_cutover():
    with tempfile.TemporaryDirectory() as dd:
        d = Path(dd)
        # simple (1 phase, no contracts/) inadequate -> exempt
        simple = _write_inflight(d, "p-9102-simple.md",
                                 _proposal(phases=1, design=_PLACEHOLDER_DESIGN))
        # complex inadequate but created before the cutover -> grandfathered
        old = _write_inflight(d, "p-9103-old.md",
                              _proposal(phases=2, design=_PLACEHOLDER_DESIGN,
                                        created="2026-06-01"))
        warns = ap._check_design_contract_adequacy([simple, old], d)
    assert warns == []


# --- create auto-emits the recall (f) ---------------------------------------

def test_create_emits_suggest_recall():  # (f)
    import proposal_suggest as _ps
    orig = _ps.suggest
    _ps.suggest = lambda desc, **k: {
        "description": desc, "similar_proposals": [], "checklist": [], "scope": [],
    }
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            pl._emit_create_recall("add a design and contract gate")
    finally:
        _ps.suggest = orig
    text = buf.getvalue()
    assert "①" in text and "②" in text and "③" in text


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
