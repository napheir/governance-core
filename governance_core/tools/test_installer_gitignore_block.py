"""Managed runtime block in the consumer .gitignore (P-0129 Phase E, F10).

The installer owns only the lines between its markers: repeated installs
keep exactly one block, every byte outside it is preserved (including CRLF
line endings), and a damaged block (begin marker, no end marker) is left
alone.

Run from repo root:
    python -m pytest tools/test_installer_gitignore_block.py -q
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance_core import installer

BEGIN = installer.GITIGNORE_BLOCK_BEGIN
END = installer.GITIGNORE_BLOCK_END


def test_empty_file_gets_block() -> None:
    text = installer._update_gitignore_text("")
    assert text.startswith(BEGIN)
    for pattern in installer.GITIGNORE_RUNTIME_PATTERNS:
        assert pattern in text


def test_existing_lines_preserved_and_block_appended() -> None:
    user = "__pycache__/\n.venv/\n"
    text = installer._update_gitignore_text(user)
    assert text.startswith(user)
    assert text.count(BEGIN) == 1


def test_missing_trailing_newline_handled() -> None:
    text = installer._update_gitignore_text("*.log")
    assert text.startswith("*.log\n")
    assert text.count(BEGIN) == 1


def test_idempotent() -> None:
    once = installer._update_gitignore_text("node_modules/\n")
    assert installer._update_gitignore_text(once) == once


def test_stale_block_replaced_in_place() -> None:
    stale = f"a/\n{BEGIN}\n/old-pattern/\n{END}\nb/\n"
    text = installer._update_gitignore_text(stale)
    assert "/old-pattern/" not in text
    assert text.startswith("a/\n") and text.endswith("b/\n")
    assert text.count(BEGIN) == 1


def test_crlf_file_keeps_crlf() -> None:
    user = "__pycache__/\r\n.venv/\r\n"
    text = installer._update_gitignore_text(user)
    assert text.startswith(user)
    assert "\n" not in text.replace("\r\n", "")  # no bare LF introduced


def test_damaged_block_left_alone() -> None:
    assert installer._update_gitignore_text(f"a/\n{BEGIN}\n/x/\n") is None


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project dir with the auth-code signature check stubbed."""
    monkeypatch.setattr(installer.codec, "verify_auth_code",
                        lambda code, key: {"consumer_id": "test-consumer"})
    root = tmp_path / "proj"
    root.mkdir()
    return root


def _install(root: Path) -> int:
    """Run a real install / upgrade into `root`."""
    return installer.install(root, config_overrides={"project_name": "proj"},
                             auth_code="stub", accept_candidate_uplink=True)


def test_install_twice_one_block_user_bytes_kept(project: Path) -> None:
    user = b"# project rules\r\n/dist/\r\n"
    (project / ".gitignore").write_bytes(user)
    assert _install(project) == 0
    assert _install(project) == 0
    data = (project / ".gitignore").read_bytes()
    assert data.startswith(user)
    assert data.count(BEGIN.encode("utf-8")) == 1
