"""Tests for Check 16a command exemption (gc #102 / P-0105).

`_audit_scenario_coverage` exempts ``source_type == "command"`` skills from the
16a coverage FAIL: slash commands are always listed in the harness Skill-tool
menu and invoked by name, so their discoverability never depends on the
SessionStart cluster/universal surfacing this gate enforces. The carve-out is
*additive* to the #101 non-hub-learned WARN tolerance (they compose), and it
leaves the 16b phantom-member check untouched. ``guide`` skills remain subject
to the FAIL.

Each fixture drives the audit with a synthetic ``.claude/`` tree (+ optional
``.governance/config.json``) under tmp_path, scanned via project_root=tmp_path,
so it is fully isolated from the running clone.

Run from repo root:
    python -m pytest governance_core/tools/test_command_coverage_exempt.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402


def _command_skill(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: command\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _guide_skill(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: guide\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _learned_skill(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: learned\ntags: [t]\n"
        f"created: 2026-06-18\nupdated: 2026-06-18\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _config(tmp: Path, consumer_id: str) -> None:
    d = tmp / ".governance"
    d.mkdir(parents=True, exist_ok=True)
    cfg = {
        "project_name": "fixture",
        "install_root": str(tmp),
        "shared_state_root": str(tmp / "shared_state"),
        "core_agent_name": "core",
        "core_branches": ["master"],
        "ritual_phrase": "ritual",
        "agents": [],
        "authorization": {"consumer_id": consumer_id},
    }
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


def _no_tiers(tmp: Path) -> Path:
    return tmp / "knowledge" / "skills" / "_tiers.json"  # absent -> no universal


def test_unsurfaced_command_neither_fails_nor_warns(tmp_path):
    # (a) A command outside the universal tier and every cluster is exempt:
    # no FAIL, no WARN -- even at the strict hub.
    _command_skill(tmp_path, "orphan-command")
    cp = _clusters(tmp_path, {"clusters": {}})
    _config(tmp_path, "governance-core")  # hub -> strict everywhere else
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp, _no_tiers(tmp_path))
    assert failed == 0
    assert warned == 0


def test_command_exempt_composes_with_nonhub_learned_warn(tmp_path):
    # (b) Composition with #101: in a non-hub clone, the command is exempt
    # (no FAIL/WARN) while an unsurfaced learned skill still WARNs.
    _command_skill(tmp_path, "orphan-command")
    _learned_skill(tmp_path, "pending-skill")
    cp = _clusters(tmp_path, {"clusters": {}})
    _config(tmp_path, "trade-agent")  # non-hub consumer
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp, _no_tiers(tmp_path))
    assert failed == 0          # command exempt, learned tolerated
    assert warned == 1          # exactly the learned skill, not the command


def test_unsurfaced_guide_still_fails(tmp_path):
    # (c) The carve-out is command-only: an unsurfaced guide still FAILs, and
    # the co-present command does not add to the failure count.
    _command_skill(tmp_path, "orphan-command")
    _guide_skill(tmp_path, "orphan-guide")
    cp = _clusters(tmp_path, {"clusters": {}})
    _config(tmp_path, "governance-core")
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp, _no_tiers(tmp_path))
    assert failed == 1          # only the guide, command is exempt


def test_phantom_member_check_unaffected(tmp_path):
    # (d) 16b (phantom member) is independent of the 16a command carve-out: a
    # cluster member with no backing skill still FAILs even when a command is
    # present and exempt.
    _command_skill(tmp_path, "real-command")
    cp = _clusters(
        tmp_path, {"clusters": {"c1": {"members": ["ghost-skill"]}}})
    _config(tmp_path, "governance-core")
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp, _no_tiers(tmp_path))
    assert failed == 1          # ghost-skill phantom; command exempt from 16a
