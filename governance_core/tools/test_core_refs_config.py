"""Core history is config-derived, not hard-coded (P-0131).

check_scope.py compared everything with a literal local `master` and tested
the core agent by the literal name "core", although config carries
`core_branches`, `upstream_branch` and `core_agent_name`; config.py read
`upstream_branch` with a `.get(key, default)` fallback (Art.4).

Run from repo root:
    python -m pytest tools/test_core_refs_config.py -q
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from governance_core import config

_CHECK_SCOPE = Path(__file__).resolve().parent / "check_scope.py"


def _code_strings(path: Path) -> list:
    """String constants in `path`, excluding docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def _compared_strings(path: Path) -> list:
    """String constants used as an operand of a comparison (==, !=, in)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            for operand in (node.left, *node.comparators):
                if isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                    found.append(operand.value)
    return found


def test_hardcoded_core_refs_absent_from_check_scope() -> None:
    strings = _code_strings(_CHECK_SCOPE)
    assert "master" not in strings
    assert not [s for s in strings if "master.." in s]
    # The core agent is topology["core"] (a dict key), never compared by name.
    assert "core" not in _compared_strings(_CHECK_SCOPE)


def test_hardcoded_core_refs_config_upstream_branch_has_no_default(tmp_path: Path) -> None:
    cfg = {"project_name": "p", "install_root": str(tmp_path),
           "shared_state_root": str(tmp_path / "s"), "claude_dir": ".claude",
           "core_agent_name": "core", "core_branches": ["master"],
           "ritual_phrase": "ok",
           "agents": [{"name": "core", "branch": "master", "clone_dir": "c"}]}
    (tmp_path / ".governance").mkdir()
    path = tmp_path / ".governance" / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert config.load_config(tmp_path).upstream_branch is None
    cfg["upstream_branch"] = "upstream/main"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    assert config.load_config(tmp_path).upstream_branch == "upstream/main"
