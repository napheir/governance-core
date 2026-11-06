"""Business clones don't offer core's learned skills; dry-run writes nothing (0.49.2).

In a multi-agent project, core's committed `.claude/skills/learned/*.md`
reach every business clone through the master merge. The business clone's
`collect` packaged them as its own candidates, its SessionStart reminder
counted them, and `sweep --dry-run` re-staged them in the outbox on every
run (deva-vani). A skill whose content core has committed is now core's to
offer; only skills authored (or edited) in the business clone are its
candidates. `sweep --dry-run` stages into a scratch directory instead of
the outbox.

Real git repos; uplink and the hub lookup are stubbed.

Run from repo root:
    python -m pytest tools/test_candidate_core_skills.py -q
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import subprocess
from pathlib import Path

import pytest

from governance_core.candidates import collect, ledger
from governance_core.tools import candidate

CORE_SKILL = "core-recipe"


def _git(repo: Path, *args: str) -> None:
    """Run a fixture git command with a throwaway identity and no hooks."""
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "core.hooksPath=.no-hooks", "-C", str(repo), *args],
                   check=True, capture_output=True)


def _skill_text(name: str, body: str = "") -> str:
    return (f"---\nname: {name}\nlayer: candidate-common\n---\n\n# {name}\n"
            f"{body}")


def _clone(tmp_path: Path, clone_dir: str) -> Path:
    """A clone of a two-agent project: core's skill committed on master,
    checked out on the agent's feature branch."""
    root = tmp_path / "proj" / clone_dir
    root.mkdir(parents=True)
    _git(root, "init", "-q", "-b", "master")
    _git(root, "config", "core.autocrlf", "true")
    cfg = {
        "project_name": "proj", "install_root": str(tmp_path),
        "shared_state_root": str(tmp_path / "proj" / "shared_state"),
        "core_agent_name": "core", "core_branches": ["master"],
        "ritual_phrase": "OK",
        "agents": [
            {"name": "core", "branch": "master", "clone_dir": "agent-core"},
            {"name": "platform", "branch": "feature/platform",
             "clone_dir": "agent-platform"}],
        "authorization": {"consumer_id": "acme"},
        "candidate_uplink": {"consent": True},
    }
    (root / ".governance").mkdir()
    (root / ".governance" / "config.json").write_text(json.dumps(cfg),
                                                      encoding="utf-8")
    (root / ".governance" / "auth_code").write_text("GC1.stub\n",
                                                    encoding="utf-8")
    skill = root / collect.LEARNED_REL / f"{CORE_SKILL}.md"
    skill.parent.mkdir(parents=True)
    skill.write_bytes(_skill_text(CORE_SKILL).encode("utf-8"))  # LF bytes
    _git(root, "add", collect.LEARNED_REL)
    _git(root, "commit", "-q", "-m", "core: add learned skill")
    _git(root, "checkout", "-q", "-b", "feature/platform")
    return root


@pytest.fixture()
def stub_uplink(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record uplinks instead of sending; no hub lookup."""
    sent: list[str] = []

    def _fake(env: Path, auth_code: str, repo: str | None = None,
              dry_run: bool = False) -> str:
        sent.append(json.loads((env / "candidate.json").read_text(
            encoding="utf-8"))["title"])
        return f"https://example.invalid/issues/{len(sent)}"

    monkeypatch.setattr(candidate._uplink, "uplink_envelope", _fake)
    monkeypatch.setattr(candidate, "_drop_pending_seen_on_hub",
                        lambda pending, led_path, origin, repo: pending)
    return sent


def _sweep(root: Path, dry_run: bool) -> str:
    ns = argparse.Namespace(project_root=str(root), repo="acme/hub",
                            dry_run=dry_run)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        assert candidate.cmd_sweep(ns) == 0
    return buf.getvalue()


def _names(paths: list[Path]) -> list[str]:
    return [p.stem for p in paths]


def test_business_clone_leaves_out_core_skill(tmp_path: Path) -> None:
    root = _clone(tmp_path, "agent-platform")
    own = root / collect.LEARNED_REL / "platform-recipe.md"
    own.write_text(_skill_text("platform-recipe"), encoding="utf-8")
    assert _names(collect.candidate_skills(root)) == ["platform-recipe"]
    assert _names(ledger.pending_candidate_skills(root)) == ["platform-recipe"]


def test_crlf_checkout_still_recognised_as_core(tmp_path: Path) -> None:
    """Windows checkouts write CRLF; git normalises it before comparing."""
    root = _clone(tmp_path, "agent-platform")
    skill = root / collect.LEARNED_REL / f"{CORE_SKILL}.md"
    lf = skill.read_bytes()
    assert b"\r\n" not in lf
    skill.write_bytes(lf.replace(b"\n", b"\r\n"))
    assert collect.candidate_skills(root) == []


def test_older_core_version_still_core(tmp_path: Path) -> None:
    """Core updated the skill after this clone merged: the clone's older copy
    is still a version core committed."""
    root = _clone(tmp_path, "agent-platform")
    skill = root / collect.LEARNED_REL / f"{CORE_SKILL}.md"
    old = skill.read_text(encoding="utf-8")
    _git(root, "checkout", "-q", "master")
    skill.write_text(_skill_text(CORE_SKILL, "\nv2\n"), encoding="utf-8")
    _git(root, "commit", "-q", "-am", "core: update skill")
    _git(root, "checkout", "-q", "feature/platform")
    assert skill.read_text(encoding="utf-8") == old
    assert collect.candidate_skills(root) == []


def test_business_edit_of_core_skill_is_offered(tmp_path: Path) -> None:
    root = _clone(tmp_path, "agent-platform")
    skill = root / collect.LEARNED_REL / f"{CORE_SKILL}.md"
    skill.write_text(_skill_text(CORE_SKILL, "\nlocal improvement\n"),
                     encoding="utf-8")
    assert _names(collect.candidate_skills(root)) == [CORE_SKILL]


def test_core_clone_offers_its_own_skill(tmp_path: Path) -> None:
    root = _clone(tmp_path, "agent-core")
    _git(root, "checkout", "-q", "master")
    assert _names(collect.candidate_skills(root)) == [CORE_SKILL]


def test_staged_core_skill_envelope_is_withdrawn(tmp_path: Path,
                                                 stub_uplink: list[str]) -> None:
    """An envelope a pre-0.49.2 collect staged for core's skill is skipped."""
    root = _clone(tmp_path, "agent-platform")
    skill = root / collect.LEARNED_REL / f"{CORE_SKILL}.md"
    collect.envelope.build_envelope(
        collect.outbox_dir(root), kind="skill", origin="acme",
        title=CORE_SKILL, rationale=f"{collect.COLLECT_RATIONALE}{skill.name}",
        payload_files=[skill], layer="candidate-common")
    out = _sweep(root, dry_run=False)
    assert stub_uplink == [], out
    assert "withdrawn" in out, out


def test_dry_run_writes_no_envelope(tmp_path: Path,
                                    stub_uplink: list[str]) -> None:
    root = _clone(tmp_path, "agent-platform")
    (root / collect.LEARNED_REL / "platform-recipe.md").write_text(
        _skill_text("platform-recipe"), encoding="utf-8")
    out = _sweep(root, dry_run=True)
    assert not collect.outbox_dir(root).exists(), out
    assert stub_uplink == ["platform-recipe"], out
    assert "1 pending candidate(s) would be uplinked" in out, out
    # the real sweep then stages and sends the same one
    _sweep(root, dry_run=False)
    assert stub_uplink == ["platform-recipe", "platform-recipe"]
    assert len(list(collect.outbox_dir(root).rglob("candidate.json"))) == 1
