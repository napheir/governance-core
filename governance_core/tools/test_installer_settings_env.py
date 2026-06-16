"""Tests for env.PYTHONUTF8 in generated settings.local.json (issue #98).

The installer natively sets `env.PYTHONUTF8 = "1"` in the generated
`.claude/settings.local.json` as defense-in-depth atop each hook's own UTF-8
byte read: without it, a fresh consumer install (no pre-existing env block to
preserve) would run hook subprocesses in the OS locale (GBK on Windows) and
risk the classify-gate fail-open class of bug. Merge-if-absent: an existing
`env` block (and any consumer override of PYTHONUTF8) is never clobbered.

Run from repo root:
    python -m pytest tools/test_installer_settings_env.py -q
"""
import json
from pathlib import Path

from governance_core import installer


def _read_settings(project_root: Path) -> dict:
    p = project_root / ".claude" / "settings.local.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_fresh_install_sets_pythonutf8(tmp_path: Path) -> None:
    """A fresh settings.local.json ships env.PYTHONUTF8 = '1'."""
    installer._write_settings_local_json(tmp_path)
    data = _read_settings(tmp_path)
    assert data["env"]["PYTHONUTF8"] == "1"


def test_merge_preserves_existing_env_keys(tmp_path: Path) -> None:
    """An existing env block is preserved; PYTHONUTF8 is added alongside."""
    sp = tmp_path / ".claude" / "settings.local.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(
        json.dumps({"env": {"FOO": "bar"}, "hooks": {}}), encoding="utf-8"
    )
    installer._write_settings_local_json(tmp_path)
    env = _read_settings(tmp_path)["env"]
    assert env["FOO"] == "bar"          # consumer key preserved
    assert env["PYTHONUTF8"] == "1"     # mitigation added


def test_existing_pythonutf8_not_clobbered(tmp_path: Path) -> None:
    """A consumer's explicit PYTHONUTF8 override is never overwritten."""
    sp = tmp_path / ".claude" / "settings.local.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(
        json.dumps({"env": {"PYTHONUTF8": "0"}, "hooks": {}}), encoding="utf-8"
    )
    installer._write_settings_local_json(tmp_path)
    assert _read_settings(tmp_path)["env"]["PYTHONUTF8"] == "0"
