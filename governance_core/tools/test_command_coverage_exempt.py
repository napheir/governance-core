"""Tests for Check 16a command exemption (gc #102 / P-0105).

`_audit_scenario_coverage` exempts source_type=="command" from the 16a coverage
FAIL: slash commands are always in the harness Skill-tool menu and invoked by
name. guides remain subject to FAIL; the 16b phantom-member check is
independent. P-0118: learned skills are always surfaced, and the universal set
derives from `theme`, so there is no _tiers.json/non-hub plumbing here.

Each fixture drives the audit with a synthetic .claude/ tree under tmp_path,
scanned via project_root=tmp_path, so it is fully isolated.

Run from repo root:
    python -m pytest governance_core/tools/test_command_coverage_exempt.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402


def _command(tmp: Path, name: str, theme: str = "core-only") -> None:
    d = tmp / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\ntheme: {theme}\nname: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _guide(tmp: Path, name: str, theme: str = "core-only") -> None:
    d = tmp / ".claude" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\ntheme: {theme}\nname: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _learned(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_unsurfaced_command_neither_fails_nor_warns(tmp_path):
    # A core-only command in no cluster is exempt: no FAIL, no WARN.
    _command(tmp_path, "orphan-command", theme="core-only")
    cp = _clusters(tmp_path, {"clusters": {}})
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 0 and warned == 0


def test_command_exempt_composes_with_learned(tmp_path):
    # P-0118: command exempt + learned always surfaced -> no FAIL, no WARN.
    _command(tmp_path, "orphan-command", theme="core-only")
    _learned(tmp_path, "solo-learned")
    cp = _clusters(tmp_path, {"clusters": {}})
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 0 and warned == 0


def test_unsurfaced_guide_still_fails(tmp_path):
    # The carve-out is command-only: an unsurfaced core-only guide still FAILs;
    # the co-present command does not add to the failure count.
    _command(tmp_path, "orphan-command", theme="core-only")
    _guide(tmp_path, "orphan-guide", theme="core-only")
    cp = _clusters(tmp_path, {"clusters": {}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 1  # only the guide


def test_phantom_member_check_unaffected(tmp_path):
    _command(tmp_path, "real-command", theme="core-only")
    cp = _clusters(tmp_path, {"clusters": {"c1": {"members": ["ghost-skill"]}}})
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 1  # ghost-skill phantom; command exempt from 16a
