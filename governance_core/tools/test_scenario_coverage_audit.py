"""Tests for audit_knowledge Check 16: scenario-surface coverage (P-0103 C, #100).

P-0118: the surfaced set is theme:universal skills + all learned (always
injected) + scenario-cluster members. Drives _audit_scenario_coverage with
synthetic .claude/skills/ files + _scenario_clusters.json under tmp_path,
scanned via project_root=tmp_path, so each fixture is isolated.

Run from repo root:
    python -m pytest tools/test_scenario_coverage_audit.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402


def _guide(tmp: Path, name: str, theme: str = "universal") -> None:
    d = tmp / ".claude" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    theme_line = f"theme: {theme}\n" if theme else ""
    (d / f"{name}.md").write_text(
        f"---\n{theme_line}name: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-16\nupdated: 2026-06-16\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _learned(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-16\nupdated: 2026-06-16\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_unsurfaced_skill_fails(tmp_path):
    # A core-only guide in no cluster is never surfaced -> FAIL; a universal one
    # is surfaced by theme.
    _guide(tmp_path, "covered-skill", theme="universal")
    _guide(tmp_path, "orphan-skill", theme="core-only")
    cp = _clusters(tmp_path, {"clusters": {"c1": {"members": ["covered-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 1  # orphan-skill core-only + unclustered


def test_all_surfaced_passes(tmp_path):
    _guide(tmp_path, "u-skill", theme="universal")
    _guide(tmp_path, "c-skill", theme="core-only")
    cp = _clusters(tmp_path, {"clusters": {"c1": {"members": ["c-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 0  # u-skill theme:universal, c-skill clustered


def test_learned_always_surfaced(tmp_path):
    # P-0118: learned skills are always injected -> always surfaced, even with
    # clusters authored and the learned skill in none of them.
    _learned(tmp_path, "solo-learned")
    cp = _clusters(tmp_path, {"clusters": {}})
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 0 and warned == 0


def test_phantom_member_fails(tmp_path):
    _guide(tmp_path, "real-skill", theme="universal")
    cp = _clusters(
        tmp_path, {"clusters": {"c1": {"members": ["real-skill", "ghost-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 1  # ghost-skill phantom
