"""audit_sub_constitutions finds sibling clones by clone_dir (P-0129 F7 family).

It built `install_root / agent-<name>`; in a nested <root>/<project>/<clone>
layout (install_root = <root>) that directory never exists, so every business
clone was reported missing and skipped (deva-vani, 0.48.1). Clones are now
located next to the running clone by their config `clone_dir`.

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
