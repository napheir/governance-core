"""Tests for audit pending-catalog tolerance in non-hub clones (gc #101 / P-0104).

Check 11a (`_audit_skill_tiers`) and Check 16a (`_audit_scenario_coverage`)
record WARN (not FAIL) for a *learned* skill that is registry-present but
catalog-absent WHEN the audited clone is a non-hub consumer. The hub stays
strict (FAIL); any ambiguity (no config) defaults to strict; and the relaxation
is learned-only (a non-learned skill still FAILs even in a non-hub clone).

Each fixture drives the audit with a synthetic ``.claude/skills/`` tree +
``.governance/config.json`` under tmp_path, scanned via project_root=tmp_path,
so it is fully isolated from the running clone.

Run from repo root:
    python -m pytest governance_core/tools/test_pending_catalog_tolerance.py -q
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402


def _learned_skill(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: learned\ntags: [t]\n"
        f"created: 2026-06-17\nupdated: 2026-06-17\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _guide_skill(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntype: guide\ntags: [t]\n"
        f"created: 2026-06-17\nupdated: 2026-06-17\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _tiers(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_tiers.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _config(tmp: Path, consumer_id) -> None:
    """Write a minimal valid .governance/config.json; consumer_id=None omits auth."""
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
    }
    if consumer_id is not None:
        cfg["authorization"] = {"consumer_id": consumer_id}
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


# ---- Check 11a: skill tier bijection (registry -> _tiers.json) ----

def test_ch11_nonhub_learned_uncataloged_warns(tmp_path):
    _learned_skill(tmp_path, "pending-skill")
    tp = _tiers(tmp_path, {"tiers": {}})
    _config(tmp_path, "trade-agent")  # non-hub consumer
    failed, warned = ak._audit_skill_tiers(tmp_path, tp)
    assert failed == 0  # uncataloged learned skill is pending, not a failure
    assert warned >= 1


def test_ch11_hub_learned_uncataloged_fails(tmp_path):
    _learned_skill(tmp_path, "pending-skill")
    tp = _tiers(tmp_path, {"tiers": {}})
    _config(tmp_path, "governance-core")  # the hub -> strict
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


def test_ch11_absent_config_strict(tmp_path):
    _learned_skill(tmp_path, "pending-skill")
    tp = _tiers(tmp_path, {"tiers": {}})
    # no .governance/config.json -> ambiguous -> default strict
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


def test_ch11_nonhub_guide_uncataloged_still_fails(tmp_path):
    # Tolerance is learned-only: a non-learned skill stays a FAIL even in a
    # non-hub clone (Non-Goal: keep the relaxation narrow).
    _guide_skill(tmp_path, "guide-skill")
    tp = _tiers(tmp_path, {"tiers": {}})
    _config(tmp_path, "trade-agent")
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


# ---- Check 11b: tiers -> registry phantom (branch-tier carve-out, gc #114) ----

# A branch-tier skill *file* is branch-local (present in exactly one clone) while
# _tiers.json is a single globally-synced hub-owned file. In a non-hub clone a
# branch entry owned by another clone is a legitimate, locally-unresolvable
# phantom -> WARN (P-0111), mirroring the 11a / 16a non-hub carve-outs. The hub
# stays strict, ambiguity (no config) defaults strict, and the relaxation is
# branch-tier-only (a universal/project phantom still FAILs).

def test_ch11b_nonhub_branch_phantom_warns(tmp_path):
    tp = _tiers(tmp_path, {"tiers": {"branch": {"skills": ["foreign-branch-skill"]}}})
    _config(tmp_path, "trade-agent")  # non-hub consumer
    failed, warned = ak._audit_skill_tiers(tmp_path, tp)
    assert failed == 0  # branch-local phantom is hub-owned & unresolvable locally
    assert warned >= 1


def test_ch11b_hub_branch_phantom_fails(tmp_path):
    tp = _tiers(tmp_path, {"tiers": {"branch": {"skills": ["foreign-branch-skill"]}}})
    _config(tmp_path, "governance-core")  # the hub -> strict
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


def test_ch11b_absent_config_strict(tmp_path):
    tp = _tiers(tmp_path, {"tiers": {"branch": {"skills": ["foreign-branch-skill"]}}})
    # no .governance/config.json -> ambiguous -> default strict
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


def test_ch11b_nonhub_universal_phantom_still_fails(tmp_path):
    # Carve-out is branch-only: a phantom in a non-branch tier stays a FAIL even
    # in a non-hub clone (Non-Goal: keep the relaxation narrow).
    tp = _tiers(tmp_path, {"tiers": {"universal": {"skills": ["ghost-skill"]}}})
    _config(tmp_path, "trade-agent")
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


def test_ch11b_nonhub_branch_and_universal_phantom_still_fails(tmp_path):
    # A phantom that ALSO lives in universal/project (home_tiers != {"branch"})
    # is a real, fixable gap and must still FAIL even in a non-hub clone.
    tp = _tiers(tmp_path, {"tiers": {
        "branch": {"skills": ["dual-home-skill"]},
        "universal": {"skills": ["dual-home-skill"]},
    }})
    _config(tmp_path, "trade-agent")
    failed, _ = ak._audit_skill_tiers(tmp_path, tp)
    assert failed >= 1


# ---- Check 16a: scenario-surface coverage ----

def test_ch16_nonhub_learned_unsurfaced_warns(tmp_path):
    _learned_skill(tmp_path, "pending-skill")
    cp = _clusters(tmp_path, {"clusters": {}})
    tp = tmp_path / "knowledge" / "skills" / "_tiers.json"  # absent -> no universal
    _config(tmp_path, "trade-agent")  # non-hub consumer
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp, tp)
    assert failed == 0
    assert warned >= 1


def test_ch16_hub_learned_unsurfaced_fails(tmp_path):
    _learned_skill(tmp_path, "pending-skill")
    cp = _clusters(tmp_path, {"clusters": {}})
    tp = tmp_path / "knowledge" / "skills" / "_tiers.json"
    _config(tmp_path, "governance-core")  # the hub -> strict
    failed, _ = ak._audit_scenario_coverage(tmp_path, cp, tp)
    assert failed >= 1
