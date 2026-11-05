"""Fresh projects get a real total constitution (P-0129 Phase D, F4).

Before, a new consumer's constitution/total.md and agent.md were stubs, so
regen produced a CLAUDE.md with no rules and the clauses never reached the
agent's context (Claude Code loads only CLAUDE.md). install now seeds
total.md from a template -- one summary + pointer per clause -- when it is
absent, and generates CLAUDE.md through the installed regen_constitution so
`--check` is in sync from the first session. Existing files are never
overwritten; a hand-written CLAUDE.md is left alone.

Runs the real installer.install() code path; only the auth-code signature
check is stubbed.

Run from repo root:
    python -m pytest tools/test_installer_constitution_seed.py -q
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from governance_core import installer


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty single-agent project dir; auth signature check stubbed."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _install(root: Path) -> int:
    """Run a real install with a single agent whose clone_dir is `root`."""
    return installer.install(root, config_overrides={
        "project_name": "Acme", "ritual_phrase": "At your service",
        "core_agent_name": "core",
        "agents": [{"name": "core", "branch": "master", "clone_dir": root.name}],
    }, auth_code="stub", accept_candidate_uplink=True)


def test_template_points_at_every_shipped_clause() -> None:
    """Completeness: a new clause must get a section in the seed template."""
    text = installer.CONSTITUTION_TEMPLATE.read_text(encoding="utf-8")
    for clause in sorted((installer.PKG_ROOT / "clauses").glob("art_*.md")):
        assert f"{installer.CLAUSES_REL}/{clause.name}" in text, clause.name


def test_fresh_install_seeds_total_and_generates_claude_md(project: Path) -> None:
    assert _install(project) == 0
    total = (project / "constitution" / "total.md").read_text(encoding="utf-8")
    assert "# Acme" in total and "At your service" in total
    assert "`core`（core）" in total
    assert "{{" not in total
    claude = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.startswith(installer.REGEN_BANNER_PREFIX)
    assert ".governance/clauses/art_13_constitution_protection.md" in claude


def test_regen_check_in_sync_after_install(project: Path) -> None:
    assert _install(project) == 0
    res = subprocess.run(
        [sys.executable, str(project / "tools" / "regen_constitution.py"),
         "--check", "--root", str(project)],
        capture_output=True, encoding="utf-8", timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr


def test_existing_total_md_untouched(project: Path) -> None:
    (project / "constitution").mkdir()
    own = project / "constitution" / "total.md"
    own.write_text("# our constitution\n", encoding="utf-8")
    assert _install(project) == 0
    assert own.read_text(encoding="utf-8") == "# our constitution\n"


def test_hand_written_claude_md_untouched(project: Path) -> None:
    hand = project / "CLAUDE.md"
    hand.write_text("# Hand-written rules\n", encoding="utf-8")
    assert _install(project) == 0
    assert hand.read_text(encoding="utf-8") == "# Hand-written rules\n"
    assert (project / "constitution" / "total.md").exists()


def test_second_install_keeps_seeded_files(project: Path) -> None:
    assert _install(project) == 0
    total = project / "constitution" / "total.md"
    total.write_text(total.read_text(encoding="utf-8") + "\n## Art.A\n",
                     encoding="utf-8")
    edited = total.read_text(encoding="utf-8")
    assert _install(project) == 0
    assert total.read_text(encoding="utf-8") == edited
