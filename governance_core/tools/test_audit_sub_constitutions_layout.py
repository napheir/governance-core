"""audit_sub_constitutions: clone lookup and what it scans (P-0129 F7 family).

It built `install_root / agent-<name>`; in a nested <root>/<project>/<clone>
layout (install_root = <root>) that directory never exists, so every business
clone was reported missing and skipped (deva-vani, 0.48.1). Clones are now
located next to the running clone by their config `clone_dir`.

It then scanned `git log --all --grep=docs(constitution)` and ran its
relaxation regexes over the whole CLAUDE.md of each hit: core's
total-constitution commits, merged into every business clone, were flagged
for the appendix's own anti-relaxation wording (deva-vani, 0.48.2). It now
scans only commits on the clone's branch that touch the agent's own
sub-constitution file, and only the lines they add.

Those regexes also hit tightening wording ("允许和禁止的表述由法务界定",
deva-vani, 0.49.1), so a hit is now a WARN for human review; only a commit
that declares `Violates-Core: YES` fails the audit.

Run from repo root:
    python -m pytest tools/test_audit_sub_constitutions_layout.py -q
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parent / "audit_sub_constitutions.py"


def test_nested_layout_business_clones_found(tmp_path: Path) -> None:
    proj = tmp_path / "root" / "deva-vani"
    agents = [{"name": "core", "branch": "master", "clone_dir": "agent-core"},
              {"name": "platform", "branch": "feature/platform",
               "clone_dir": "agent-platform"}]
    core = proj / "agent-core"
    (core / ".governance").mkdir(parents=True)
    (core / ".governance" / "config.json").write_text(json.dumps({
        "install_root": str(tmp_path / "root"), "core_agent_name": "core",
        "agents": agents}), encoding="utf-8")
    (core / "tools").mkdir()
    shutil.copy2(_TOOL, core / "tools" / _TOOL.name)
    platform = proj / "agent-platform"
    platform.mkdir()
    subprocess.run(["git", "init", "-q", str(platform)], check=True)

    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    res = subprocess.run([sys.executable, str(core / "tools" / _TOOL.name)],
                         capture_output=True, encoding="utf-8", errors="replace",
                         timeout=60, env=env, cwd=str(core))
    out = res.stdout + res.stderr
    assert "agent-platform (platform)" in out, out
    assert "不存在" not in out, out


APPENDIX_LINE = ("子宪法**禁止修改、放宽或豁免**总宪法核心准则，"
                 "只能引用或补充细节（红线）\n")


def _git(repo: Path, *args: str) -> None:
    """Run a fixture git command with a throwaway identity and no hooks."""
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "-c", "core.hooksPath=.no-hooks", "-C", str(repo), *args],
                   check=True, capture_output=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _project_with_merged_core_constitution(tmp_path: Path) -> tuple:
    """Nested project whose platform clone merged a core total-constitution
    commit (docs(constitution), appendix wording in CLAUDE.md) from master."""
    proj = tmp_path / "root" / "proj"
    agents = [{"name": "core", "branch": "master", "clone_dir": "agent-core"},
              {"name": "platform", "branch": "feature/platform",
               "clone_dir": "agent-platform"}]
    core = proj / "agent-core"
    _write(core, ".governance/config.json", json.dumps({
        "install_root": str(tmp_path / "root"), "core_agent_name": "core",
        "agents": agents}))
    (core / "tools").mkdir()
    shutil.copy2(_TOOL, core / "tools" / _TOOL.name)

    platform = proj / "agent-platform"
    platform.mkdir()
    _git(platform, "init", "-q", "-b", "master")
    _write(platform, "constitution/agent.md", "# per-agent sub-constitution (stub)\n")
    _write(platform, "constitution/total.md", "# total\n")
    _write(platform, "CLAUDE.md", "# total\n")
    _git(platform, "add", "-A")
    _git(platform, "commit", "-q", "-m", "chore: bootstrap")
    _git(platform, "checkout", "-q", "-b", "feature/platform")
    _git(platform, "checkout", "-q", "master")
    _write(platform, "constitution/total.md", "# total\n" + APPENDIX_LINE)
    _write(platform, "constitution/agent.core.md", "# core\n可以豁免硬编码配置\n")
    _write(platform, "CLAUDE.md", "# total\n" + APPENDIX_LINE)
    _git(platform, "add", "-A")
    _git(platform, "commit", "-q", "-m", "docs(constitution): add appendix")
    _git(platform, "checkout", "-q", "feature/platform")
    _git(platform, "merge", "-q", "--no-ff", "-m", "merge master", "master")
    return core, platform


def _run_audit(core: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, str(core / "tools" / _TOOL.name)],
                          capture_output=True, encoding="utf-8", errors="replace",
                          timeout=60, env=env, cwd=str(core))


def test_merged_core_constitution_commit_not_flagged(tmp_path: Path) -> None:
    core, _platform = _project_with_merged_core_constitution(tmp_path)
    res = _run_audit(core)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "潜在违规" not in out, out


def _commit_sub_constitution(platform: Path, line: str, violates: str) -> None:
    """Add `line` to the platform agent's sub-constitution in a templated
    [CONSTITUTION_CHANGE] commit declaring `Violates-Core: <violates>`."""
    _write(platform, "constitution/agent.md",
           "# per-agent sub-constitution (stub)\n" + line + "\n")
    _git(platform, "commit", "-q", "-am",
         "docs(constitution): platform rule\n\n[CONSTITUTION_CHANGE]\n"
         "- Article: 第四条\n- Scope: agent-only\n- Type: add-detail\n"
         f"- Violates-Core: {violates}\n")


def test_keyword_hit_is_review_warning_not_failure(tmp_path: Path) -> None:
    """A regex hit is listed for human review but does not fail the audit."""
    core, platform = _project_with_merged_core_constitution(tmp_path)
    _commit_sub_constitution(platform, "本 agent 可以豁免硬编码配置", "NO")
    res = _run_audit(core)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "人工复核" in out and "第四条" in out, out
    assert "本 agent 可以豁免硬编码配置" in out, out


def test_tightening_wording_does_not_fail(tmp_path: Path) -> None:
    """deva-vani content P-0005: a restriction that names 允许 and 禁止."""
    core, platform = _project_with_merged_core_constitution(tmp_path)
    _commit_sub_constitution(
        platform, "允许和禁止的表述由法务界定，写进 brand_voice 契约的红线", "NO")
    res = _run_audit(core)
    out = res.stdout + res.stderr
    assert res.returncode == 0, out
    assert "[FAIL]" not in out, out


def test_declared_violation_fails(tmp_path: Path) -> None:
    core, platform = _project_with_merged_core_constitution(tmp_path)
    _commit_sub_constitution(platform, "本 agent 的提交说明另行约定", "YES")
    res = _run_audit(core)
    out = res.stdout + res.stderr
    assert res.returncode == 1, out
    assert "Violates-Core: YES" in out, out
