"""Tests for the bounded SessionStart skill menu (P-0103 part A, issue #100).

The hub has 0 learned skills, so the discovery regression is not hub-dogfoodable
(cf. the consumer's ~50 skills); these drive the reader with synthetic
_tiers.json / _scenario_clusters.json fixtures under tmp_path. Each registry is
constructed with project_root=tmp_path, so the usage funnel writes under the
fixture, not the real repo.

Run from repo root:
    python -m pytest tools/test_skill_injection_bounded.py -q
"""
import json
from pathlib import Path

from governance_core.discovery.registry import (
    SkillRegistry,
    emit_bounded_injection,
    _UNIVERSAL_INJECTION_LIMIT,
)


def _make_skill(d: Path, name: str, desc: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\ntheme: universal\nname: {name}\ndescription: {desc}\n"
        f"type: guide\ntags: [t]\ncreated: 2026-06-16\nupdated: 2026-06-16\n"
        f"---\n\n# {name}\n",
        encoding="utf-8",
    )


def _project(tmp: Path, tiers=None, clusters=None) -> SkillRegistry:
    # Real skill files so the registry resolves descriptions.
    _make_skill(tmp / ".claude" / "skills", "alpha-skill", "Alpha does A.")
    _make_skill(tmp / ".claude" / "skills" / "learned", "beta-skill", "Beta does B.")
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    if tiers is not None:
        (sk / "_tiers.json").write_text(json.dumps(tiers), encoding="utf-8")
    if clusters is not None:
        (sk / "_scenario_clusters.json").write_text(
            json.dumps(clusters), encoding="utf-8"
        )
    reg = SkillRegistry(project_root=tmp)
    reg.scan()
    return reg


def test_none_when_no_index(tmp_path):
    """No _tiers / _scenario_clusters -> None (caller falls back to counts)."""
    reg = _project(tmp_path)
    assert emit_bounded_injection(reg) is None


def test_universal_names_and_desc(tmp_path):
    reg = _project(
        tmp_path, tiers={"tiers": {"universal": {"skills": ["alpha-skill"]}}}
    )
    out = emit_bounded_injection(reg)
    assert out is not None
    assert "alpha-skill" in out and "Alpha does A." in out
    assert "Universal" in out


def test_cluster_map(tmp_path):
    reg = _project(
        tmp_path,
        clusters={"clusters": {"release-pipeline": {
            "description": "ship a version", "members": ["alpha-skill", "beta-skill"]}}},
    )
    out = emit_bounded_injection(reg)
    assert out is not None
    assert "release-pipeline" in out
    assert "alpha-skill, beta-skill" in out
    assert "ship a version" in out


def test_universal_capped(tmp_path):
    many = [f"s{i}" for i in range(_UNIVERSAL_INJECTION_LIMIT + 5)]
    reg = _project(tmp_path, tiers={"tiers": {"universal": {"skills": many}}})
    out = emit_bounded_injection(reg)
    shown = [ln for ln in out.splitlines() if ln.startswith("    s")]
    assert len(shown) <= _UNIVERSAL_INJECTION_LIMIT
    assert "+5 more" in out


def test_bounded_line_ceiling(tmp_path):
    """The menu stays bounded -- NOT the ~55-line full dump C3 removed."""
    reg = _project(
        tmp_path,
        tiers={"tiers": {"universal": {"skills": ["alpha-skill"]}}},
        clusters={"clusters": {"c1": {"members": ["beta-skill"]}}},
    )
    out = emit_bounded_injection(reg)
    assert len(out.splitlines()) < 40


def test_records_surfaced(tmp_path):
    """Path-A surfacing is recorded on the live emit (revives the funnel arm)."""
    reg = _project(
        tmp_path, tiers={"tiers": {"universal": {"skills": ["alpha-skill"]}}}
    )
    emit_bounded_injection(reg)
    row = reg._get_tracker().funnel_row("alpha-skill")
    assert row["surfaced_count"] >= 1
