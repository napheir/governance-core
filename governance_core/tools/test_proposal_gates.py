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
from proposal_lib import approval_criteria_adequacy  # noqa: E402


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
