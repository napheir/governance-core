"""Tests for audit_knowledge Check 16: scenario-surface coverage (P-0103 C, #100).

Drives _audit_scenario_coverage with synthetic .claude/skills/ files +
_scenario_clusters.json / _tiers.json under tmp_path. The audit registry is
constructed with project_root=tmp_path, so each fixture is isolated.

Run from repo root:
    python -m pytest tools/test_scenario_coverage_audit.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402


def _skill(d: Path, name: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: guide\ntags: [t]\n"
        f"created: 2026-06-16\nupdated: 2026-06-16\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _tiers(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_tiers.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_unsurfaced_skill_fails(tmp_path):
    _skill(tmp_path / ".claude" / "skills", "covered-skill")
    _skill(tmp_path / ".claude" / "skills", "orphan-skill")
    cp = _clusters(tmp_path, {"clusters": {"c1": {"members": ["covered-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(
        tmp_path, cp, tmp_path / "knowledge" / "skills" / "_tiers.json")
    assert failed == 1  # orphan-skill is neither universal nor clustered


def test_all_surfaced_passes(tmp_path):
    _skill(tmp_path / ".claude" / "skills", "u-skill")
    _skill(tmp_path / ".claude" / "skills", "c-skill")
    tp = _tiers(tmp_path, {"tiers": {"universal": {"skills": ["u-skill"]}}})
    cp = _clusters(tmp_path, {"clusters": {"c1": {"members": ["c-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp, tp)
    assert failed == 0  # u-skill universal, c-skill clustered


def test_phantom_member_fails(tmp_path):
    _skill(tmp_path / ".claude" / "skills", "real-skill")
    cp = _clusters(
        tmp_path, {"clusters": {"c1": {"members": ["real-skill", "ghost-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(
        tmp_path, cp, tmp_path / "knowledge" / "skills" / "_tiers.json")
    assert failed == 1  # ghost-skill is a phantom member
