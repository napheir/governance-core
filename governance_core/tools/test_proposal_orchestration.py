"""P-0134: a proposal can opt in to Workflow (multi-agent) execution.

`orchestration: workflow` marks a proposal whose work runs as a Claude Code
Workflow at the scale its `### Workflow Execution` section declares; the
owner's approval is the opt-in. `workflow_declaration_adequacy` is the shared
FORM predicate behind the approve BLOCK (no exemption) and audit Check 22.
Grammar: contracts/proposal_gate_schema.md §5.

Run from repo root:
    python -m pytest tools/test_proposal_orchestration.py -q
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_proposals as ap  # noqa: E402
import proposal_lib as pl  # noqa: E402

DECLARATION = (
    "### Workflow Execution\n\n"
    "> **[TOKEN WARNING]** 以 Workflow 执行会大幅增加 token 用量：约 6 个代理，约为单会话的 5 倍。\n\n"
    "- Parallelism: one reviewer per dimension; dimensions do not depend on each other\n"
    "- Scale: 2 phases, 3 agents each, 6 total (under medium)\n"
    "- Cost: roughly 5x a single session, about 20 minutes\n"
    "- Write scope: read-only reports under artifacts/core/\n"
    "- Verification: each finding re-checked by a second agent\n"
    "- Failure & resume: resumeFromRunId, or re-run the failed phase only\n"
)
CONSENT = ("- [ ] Owner consents to Workflow execution at 6 agents — "
           "human-verify: owner approves the Workflow scale and cost\n")
GENERIC = "- [ ] Design reviewed — human-verify: reviewer signs off\n"


def _body(declaration: str = DECLARATION, criteria: str = CONSENT) -> str:
    return ("# Proposal P-9100: Fixture\n\n"
            "## Current State (read, not assumed)\n\nRead `tools/x.py:1`.\n\n"
            "## Scope\n\nadjust a helper\n\n"
            f"## Design & Contract\n\n{declaration}\n"
            "## Non-Goals\n\nnone\n\n"
            "## Phases\n\n### Phase 1: Review\n\n- gate: cmd: true\n"
            "- calibration: neg broken -> FAIL; golden good -> PASS\n\n"
            f"## Approval Criteria\n\n{criteria}")


def _file(tmp_path: Path, body: str, *, status: str = "pending",
          extra_fm: str = "orchestration: workflow\n") -> Path:
    path = tmp_path / "p-9100-fixture.md"
    path.write_text(f"---\nid: P-9100\nagent: core\nstatus: {status}\n"
                    f"created: 2026-11-06\n{extra_fm}---\n\n{body}",
                    encoding="utf-8")
    return path


@pytest.fixture()
def seams(monkeypatch: pytest.MonkeyPatch):
    """Point proposal_lib at one temp proposal file; no corpus or snapshots."""
    holder: dict = {}
    monkeypatch.setattr(pl, "find_by_id", lambda pid: holder["path"])
    monkeypatch.setattr(pl, "_lock_path",
                        lambda: holder["path"].parent / ".proposal.lock")
    monkeypatch.setattr(pl, "_lock_timeout", lambda: 5)
    monkeypatch.setattr(pl, "_write_snapshot", lambda *a, **k: None)
    return holder


# --- predicate ----------------------------------------------------------------

def test_complete_declaration_passes() -> None:
    assert pl.workflow_declaration_adequacy(_body()) == (True, "ok")


def test_missing_section_fails() -> None:
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration="nothing\n"))
    assert not ok and "Workflow Execution" in reason


def test_warning_must_be_first_line() -> None:
    moved = DECLARATION.replace(
        "> **[TOKEN WARNING]**", "Intro line.\n\n> **[TOKEN WARNING]**")
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration=moved))
    assert not ok and "first line" in reason


def test_placeholder_warning_fails() -> None:
    body = _body(declaration=pl._WORKFLOW_SKELETON)
    ok, reason = pl.workflow_declaration_adequacy(body)
    assert not ok and "TOKEN WARNING" in reason


@pytest.mark.parametrize("label", pl._WORKFLOW_LABELS)
def test_each_label_required(label: str) -> None:
    kept = "".join(line for line in DECLARATION.splitlines(keepends=True)
                   if not line.startswith(f"- {label}:"))
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration=kept))
    assert not ok and label in reason


@pytest.mark.parametrize("value", ["<to be decided>", "TBD", ""])
def test_placeholder_label_fails(value: str) -> None:
    decl = DECLARATION.replace(
        "- Cost: roughly 5x a single session, about 20 minutes", f"- Cost: {value}")
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration=decl))
    assert not ok and "Cost" in reason


def test_scale_needs_a_number() -> None:
    decl = DECLARATION.replace("2 phases, 3 agents each, 6 total (under medium)",
                               "a few agents")
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration=decl))
    assert not ok and "Scale" in reason


def test_generic_human_verify_is_not_consent() -> None:
    ok, reason = pl.workflow_declaration_adequacy(_body(criteria=GENERIC))
    assert not ok and "consent" in reason


def test_fenced_example_is_not_the_section() -> None:
    fenced = "```markdown\n" + DECLARATION + "```\n"
    ok, reason = pl.workflow_declaration_adequacy(_body(declaration=fenced))
    assert not ok and "missing" in reason


# --- scaffold -------------------------------------------------------------------

def test_scaffold_with_orchestration() -> None:
    text = pl._v2_scaffold("P-0001", "Demo", "core", "workflow")
    assert "\norchestration: workflow\n" in text.split("\n---\n", 1)[0] + "\n"
    body = text.split("\n---\n", 1)[1]
    assert (body.index("## Design & Contract") < body.index(pl._WORKFLOW_HEADING)
            < body.index("## Non-Goals"))
    assert pl._has_workflow_consent(body)
    ok, _ = pl.workflow_declaration_adequacy(body)
    assert not ok  # the skeleton is placeholders until filled
    # the new H3 ends the Flow sub-part; it does not leak into it
    flow = pl._extract_h3(pl._extract_section(body, "## Design & Contract"), "### Flow")
    assert flow is not None and "TOKEN WARNING" not in flow


def test_default_scaffold_has_hint_but_no_section() -> None:
    text = pl._v2_scaffold("P-0001", "Demo", "core")
    assert "orchestration" not in text.split("\n---\n", 1)[0]
    assert pl._WORKFLOW_HEADING + "\n" not in text
    assert "--orchestration workflow" in text


# --- approve gate --------------------------------------------------------------

def test_approve_blocks_incomplete_declaration(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(criteria=GENERIC))
    with pytest.raises(ValueError, match="workflow-declaration gate"):
        pl.transition_proposal("P-9100", "approved", note="owner: ok")


def test_approve_allows_complete_declaration(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body())
    _, prev, new = pl.transition_proposal("P-9100", "approved", note="owner: ok")
    assert (prev, new) == ("pending", "approved")


def test_non_orchestrated_proposal_not_gated(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(declaration="plain\n", criteria=GENERIC),
                          extra_fm="")
    _, _, new = pl.transition_proposal("P-9100", "approved", note="owner: ok")
    assert new == "approved"


def test_no_exemption_flag() -> None:
    params = inspect.signature(pl.transition_proposal).parameters
    assert not any("workflow" in name for name in params)


# --- orchestrate ----------------------------------------------------------------

def test_set_and_clear_on_draft(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(declaration="plain\n", criteria=GENERIC),
                          status="draft", extra_fm="")
    _, changed = pl.set_orchestration("P-9100", "workflow")
    fm, body = pl.parse_proposal(seams["path"])
    assert changed and pl.is_orchestrated(fm)
    assert pl._workflow_section(body) is not None and pl._has_workflow_consent(body)
    assert "orchestration set to workflow" in body
    assert pl.set_orchestration("P-9100", "workflow")[1] is False
    _, changed = pl.set_orchestration("P-9100", None)
    fm, _ = pl.parse_proposal(seams["path"])
    assert changed and "orchestration" not in fm


def test_orchestrate_refused_after_draft(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(), status="pending", extra_fm="")
    with pytest.raises(ValueError, match="draft"):
        pl.set_orchestration("P-9100", "workflow")


def test_orchestrate_cli_needs_set_or_clear() -> None:
    with pytest.raises(SystemExit):
        pl.main(["orchestrate", "--id", "P-9100"])


# --- run --------------------------------------------------------------------------

def test_run_shows_declaration_without_gates(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(), status="approved")
    result = pl.run_proposal("P-9100")
    assert result["results"] == []
    assert result["declaration"].startswith("> **[TOKEN WARNING]**")


def test_run_orchestrated_execution_class_lists_gates(tmp_path: Path,
                                                      seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(), status="approved",
                          extra_fm="orchestration: workflow\nexecution: gates\n")
    result = pl.run_proposal("P-9100")
    assert [r["status"] for r in result["results"]] == ["dry-run"]
    assert "declaration" in result


def test_run_refuses_plain_proposal(tmp_path: Path, seams: dict) -> None:
    seams["path"] = _file(tmp_path, _body(), status="approved", extra_fm="")
    with pytest.raises(ValueError, match="nothing to run"):
        pl.run_proposal("P-9100")


# --- audit Check 22 --------------------------------------------------------------

def test_audit_check22_agrees_with_gate(tmp_path: Path) -> None:
    bad = _file(tmp_path, _body(criteria=GENERIC))
    warnings = ap._check_workflow_declaration([bad])
    _, reason = pl.workflow_declaration_adequacy(_body(criteria=GENERIC))
    assert len(warnings) == 1 and "Check 22" in warnings[0] and reason in warnings[0]


def test_audit_check22_silent_when_complete_plain_or_draft(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "c").mkdir()
    good = _file(tmp_path / "a", _body())
    plain = _file(tmp_path / "b", _body(criteria=GENERIC), extra_fm="")
    draft = _file(tmp_path / "c", _body(criteria=GENERIC), status="draft")
    assert ap._check_workflow_declaration([good, plain, draft]) == []
