"""Tests for the P-0119 signed Approval-Criteria gate (Phase 1).

`approval_criteria_adequacy` is a FORM-only check: every `## Approval Criteria`
checklist item must carry one check token (cmd: / agent-rubric: / human-verify:).
It drives body strings directly -- no fixtures needed.

Run from repo root:
    python -m pytest tools/test_proposal_gates.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
from proposal_lib import (  # noqa: E402
    approval_criteria_adequacy,
    gate_calibration_adequacy,
    _phase_blocks,
    _extract_gate_token,
)


def _body(criteria: str) -> str:
    return f"# Proposal P-9999: x\n\n## Approval Criteria\n\n{criteria}\n"


def test_signed_cmd_item_passes():
    ok, _ = approval_criteria_adequacy(_body(
        "- [ ] tests pass -- cmd: python -m pytest tools/test_x.py"))
    assert ok


def test_human_verify_token_passes():
    ok, _ = approval_criteria_adequacy(_body(
        "- [ ] design reviewed -- human-verify: reviewer signs off"))
    assert ok


def test_agent_rubric_token_passes():
    ok, _ = approval_criteria_adequacy(_body(
        "- [ ] output well-formed -- agent-rubric: knowledge/rubric.md"))
    assert ok


def test_unsigned_item_fails():
    ok, reason = approval_criteria_adequacy(_body("- [ ] it works well"))
    assert not ok
    assert "check token" in reason


def test_mixed_fails_on_the_unsigned_one():
    ok, _ = approval_criteria_adequacy(_body(
        "- [ ] a -- cmd: true\n- [ ] b (no token)\n"))
    assert not ok


def test_no_section_passes():
    ok, _ = approval_criteria_adequacy(
        "# Proposal P-9999: x\n\n## Scope\n\nfoo\n")
    assert ok


def test_no_items_passes():
    # only a guidance blockquote, no checklist items
    ok, _ = approval_criteria_adequacy(_body("> guidance, not an item"))
    assert ok


def test_token_on_continuation_line_passes():
    ok, _ = approval_criteria_adequacy(_body(
        "- [ ] a longer acceptance that wraps\n"
        "      cmd: python -m pytest x.py"))
    assert ok


def test_guidance_blockquote_not_counted():
    # a `>` line with no token must NOT be treated as an unsigned item
    ok, _ = approval_criteria_adequacy(_body(
        "> Each item pairs acceptance with a check.\n"
        "- [ ] a -- cmd: true"))
    assert ok


def test_checked_box_item_also_gated():
    # a `- [x]` (checked) item still needs a token
    ok, _ = approval_criteria_adequacy(_body("- [x] done but no token"))
    assert not ok


# ---- Phase 2: execution-class gate calibration ----

_GOOD_PHASE = (
    "### Phase 1: do the thing\n"
    "- Deliverables: x\n"
    "- gate: cmd: python -m pytest tools/test_x.py\n"
    "- calibration: neg tests/broken -> FAIL; golden tests/good -> PASS\n"
    "- Exit criteria: y\n"
)


def _exec_body(phases: str) -> str:
    return f"# Proposal P-9999: x\n\n## Phases\n\n{phases}\n"


def test_calibration_good_phase_passes():
    ok, _ = gate_calibration_adequacy(_exec_body(_GOOD_PHASE))
    assert ok


def test_calibration_missing_gate_fails():
    ok, _ = gate_calibration_adequacy(_exec_body(
        "### Phase 1: x\n- calibration: neg a -> FAIL; golden b -> PASS\n"))
    assert not ok


def test_calibration_missing_calibration_fails():
    ok, _ = gate_calibration_adequacy(_exec_body(
        "### Phase 1: x\n- gate: cmd: true\n"))
    assert not ok


def test_calibration_missing_neg_fails():
    ok, _ = gate_calibration_adequacy(_exec_body(
        "### Phase 1: x\n- gate: cmd: true\n- calibration: golden b -> PASS\n"))
    assert not ok


def test_calibration_no_real_phase_fails():
    ok, _ = gate_calibration_adequacy(_exec_body("### Phase 0: <placeholder>\n"))
    assert not ok


def test_phase_blocks_skips_placeholder():
    body = _exec_body("### Phase 0: <x>\n- a\n" + _GOOD_PHASE)
    blocks = _phase_blocks(body)
    assert len(blocks) == 1  # only the real phase
    assert "do the thing" in blocks[0][0]


def test_extract_gate_token():
    kind, val = _extract_gate_token("- gate: cmd: python x.py\n")
    assert kind == "cmd" and val == "python x.py"


def test_extract_gate_token_none():
    assert _extract_gate_token("- Deliverables: no gate here\n") is None
