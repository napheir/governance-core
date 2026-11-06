"""candidate.py sweep: relabelling a collected skill withdraws it (0.49.1).

`sweep` uplinked every envelope in the outbox that the ledger did not know,
without looking at the learned skill it came from. A skill the owner
relabelled `layer: business` after `collect` had staged it was still posted
as a public hub issue (deva-vani). A collected skill envelope whose learned
file is no longer candidate-common (relabelled or deleted) is now skipped.
Drift and /submit-candidate envelopes are not tied to a learned skill and
are unaffected.

Key-free: the uplink itself and the hub lookup are stubbed; the selection
logic in cmd_sweep runs as in production.

Run from repo root:
    python -m pytest tools/test_candidate_sweep_withdrawn.py -q
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path

import pytest

from governance_core.candidates import collect, envelope
from governance_core.tools import candidate


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """An authorized consumer project; uplinks are recorded, not sent."""
    root = tmp_path / "proj"
    (root / ".governance").mkdir(parents=True)
    (root / ".governance" / "config.json").write_text(json.dumps({
        "authorization": {"consumer_id": "acme"},
        "candidate_uplink": {"consent": True}}), encoding="utf-8")
    (root / ".governance" / "auth_code").write_text("GC1.stub\n",
                                                    encoding="utf-8")
    sent: list[str] = []

    def _fake_uplink(env: Path, auth_code: str, repo: str | None = None,
                     dry_run: bool = False) -> str:
        sent.append(env.name)
        return f"https://example.invalid/issues/{len(sent)}"

    monkeypatch.setattr(candidate._uplink, "uplink_envelope", _fake_uplink)
    monkeypatch.setattr(candidate, "_drop_pending_seen_on_hub",
                        lambda pending, led_path, origin, repo: pending)
    return {"root": root, "sent": sent}


def _skill(root: Path, name: str, layer: str) -> Path:
    """Write a learned skill with the given `layer:` frontmatter."""
    path = root / collect.LEARNED_REL / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\nlayer: {layer}\n---\n\n# {name}\n",
                    encoding="utf-8")
    return path


def _sweep(root: Path) -> str:
    """Run a real (non-dry-run) sweep; return its stdout."""
    ns = argparse.Namespace(project_root=str(root), repo="acme/hub",
                            dry_run=False)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert candidate.cmd_sweep(ns) == 0
    return buf.getvalue()


def _staged(root: Path) -> list[Path]:
    """Envelope dirs currently in the outbox."""
    return sorted({p.parent for p in
                   collect.outbox_dir(root).rglob("candidate.json")})


def test_relabelled_skill_is_not_uplinked(project: dict) -> None:
    root = project["root"]
    skill = _skill(root, "private-recipe", "candidate-common")
    assert collect.collect_netnew_skills(root, "acme")
    skill.write_text(skill.read_text(encoding="utf-8").replace(
        "layer: candidate-common", "layer: business"), encoding="utf-8")
    out = _sweep(root)
    assert project["sent"] == [], out
    assert "withdrawn" in out and "private-recipe.md" in out, out


def test_deleted_skill_is_not_uplinked(project: dict) -> None:
    root = project["root"]
    skill = _skill(root, "gone", "candidate-common")
    assert collect.collect_netnew_skills(root, "acme")
    skill.unlink()
    out = _sweep(root)
    assert project["sent"] == [], out
    assert "withdrawn" in out, out


def test_candidate_common_skill_still_uplinked(project: dict) -> None:
    root = project["root"]
    _skill(root, "shared-recipe", "candidate-common")
    _sweep(root)
    assert len(project["sent"]) == 1


def test_relabelled_back_is_uplinked_once(project: dict) -> None:
    root = project["root"]
    skill = _skill(root, "flip", "candidate-common")
    assert collect.collect_netnew_skills(root, "acme")
    text = skill.read_text(encoding="utf-8")
    skill.write_text(text.replace("candidate-common", "business"),
                     encoding="utf-8")
    _sweep(root)
    skill.write_text(text, encoding="utf-8")
    _sweep(root)
    assert len(project["sent"]) == 1
    assert len(_staged(root)) == 1


def test_submitted_envelope_not_tied_to_learned_skill(project: dict) -> None:
    """A /submit-candidate skill envelope is uplinked even when a business
    learned skill shares its title."""
    root = project["root"]
    payload = root / "artifacts" / "tool.md"
    payload.parent.mkdir(parents=True)
    payload.write_text("# tool\n", encoding="utf-8")
    envelope.build_envelope(collect.outbox_dir(root), kind="skill",
                            origin="acme", title="tool",
                            rationale="offered by the owner",
                            payload_files=[payload])
    _skill(root, "tool", "business")
    _sweep(root)
    assert len(project["sent"]) == 1
