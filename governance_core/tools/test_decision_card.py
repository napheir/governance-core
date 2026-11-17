# -*- coding: utf-8 -*-
"""Tests for P-0139: the owner decision card as a gc capability.

Covers:
  - _v2_scaffold opens with `## Decision Card` (before Trigger), placeholder-only
  - decision_card_adequacy() form-only truth table (missing / placeholder /
    empty / too long / ok; `>` guidance lines not counted)
  - transition_proposal to pending / approved WARNs on a bad card, never
    blocks, and --allow-no-card silences it
  - the shipped guide is theme: universal, and the per-prompt reminder names it

Run from repo root:
    python -m pytest tools/test_decision_card.py -q
"""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import proposal_lib as pl

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_SKILLS = next(p for p in (_ROOT / "skills", _ROOT / ".claude" / "skills")
               if (p / "owner-decision-card.md").is_file())
_HOOKS = next(p for p in (_ROOT / "hooks", _ROOT / ".claude" / "hooks")
              if (p / "constitution-reminder.py").is_file())

_CARD_OK = (
    "- What changes: X.\n- Cost: one phase.\n- Risk: low.\n- Undo: revert.\n"
    "- Notice: a WARN.\n- Defaults: A, B.\n"
)


def _body(card: str | None) -> str:
    section = "" if card is None else f"## Decision Card\n\n{card}\n"
    return (f"# Proposal P-9200: Fixture\n\n{section}"
            "## Trigger\n\nx\n\n## Current State (read, not assumed)\n\n"
            "Read `tools/proposal_lib.py:1` today.\n\n## Scope\n\ny\n")


# --- scaffold -----------------------------------------------------------------

def test_scaffold_opens_with_the_card() -> None:
    body = pl._v2_scaffold("P-0001", "Demo", "core")
    assert body.count("## Decision Card") == 1
    assert body.index("# Proposal") < body.index("## Decision Card") < body.index("## Trigger")
    ok, reason = pl.decision_card_adequacy(body)
    assert not ok and "placeholder" in reason


# --- decision_card_adequacy -----------------------------------------------------

def test_missing_section() -> None:
    ok, reason = pl.decision_card_adequacy(_body(None))
    assert not ok and "no '## Decision Card'" in reason


def test_empty_card_with_only_guidance() -> None:
    ok, reason = pl.decision_card_adequacy(_body("> guidance only\n"))
    assert not ok and "empty" in reason


def test_too_long() -> None:
    card = "".join(f"- line {i}\n" for i in range(9))
    ok, reason = pl.decision_card_adequacy(_body(card))
    assert not ok and "9 lines" in reason


def test_ok_and_guidance_not_counted() -> None:
    assert pl.decision_card_adequacy(_body(_CARD_OK)) == (True, "ok")
    card = "> one\n> two\n> three\n\n" + "".join(f"- line {i}\n" for i in range(8))
    assert pl.decision_card_adequacy(_body(card))[0]


# --- transition WARN, never BLOCK -----------------------------------------------

@contextlib.contextmanager
def _seams(path: Path):
    """Run transition_proposal against a lone temp file."""
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


def _submit(card: str | None, **kw) -> tuple:
    """draft -> pending on a temp proposal; returns (new_status, stderr)."""
    with tempfile.TemporaryDirectory() as dd:
        p = Path(dd) / "p-9200-fixture.md"
        p.write_text("---\nid: P-9200\nagent: core\nstatus: draft\ncreated: 2026-11-17\n"
                     "owner: core\n---\n\n" + _body(card), encoding="utf-8")
        err = io.StringIO()
        with _seams(p), contextlib.redirect_stderr(err):
            _, _, new = pl.transition_proposal("P-9200", "pending", note="submit", **kw)
        return new, err.getvalue()


def test_bad_card_warns_but_submit_goes_through() -> None:
    new, err = _submit("<decision card>")
    assert new == "pending"
    assert "[WARN] P-9200: decision-card gate -- the decision card is still the placeholder" in err


def test_good_card_is_silent() -> None:
    assert _submit(_CARD_OK) == ("pending", "")


def test_allow_no_card_silences_it() -> None:
    assert _submit(None, allow_no_card=True) == ("pending", "")


def test_cli_has_the_flag() -> None:
    res = subprocess.run([sys.executable, str(_HERE / "proposal_lib.py"), "transition", "-h"],
                         capture_output=True, encoding="utf-8")
    assert "--allow-no-card" in res.stdout


# --- guide and reminder ---------------------------------------------------------

def test_guide_is_universal() -> None:
    text = (_SKILLS / "owner-decision-card.md").read_text(encoding="utf-8")
    head = text.split("---")[1]
    assert "theme: universal" in head and "name: owner-decision-card" in head
    assert "At most 8 lines" in text


def test_reminder_names_the_guide() -> None:
    res = subprocess.run([sys.executable, str(_HOOKS / "constitution-reminder.py")],
                         input=json.dumps({"prompt": "hi"}), capture_output=True,
                         encoding="utf-8")
    assert res.returncode == 0
    assert "owner-decision-card" in res.stdout and "Art.0" in res.stdout
