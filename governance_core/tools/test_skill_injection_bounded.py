"""Tests for the bounded SessionStart skill menu (P-0103 part A, issue #100).

P-0118 reworked the universal-pool derivation: it now reads each skill's
pre-existing ``theme:`` frontmatter (sync_infra's breadth field) instead of a
central ``knowledge/skills/_tiers.json``. The pool is every ``learned`` skill
(this agent's own) plus every ``guide`` whose ``theme == "universal"``. These
drive the reader with synthetic skill files + ``_scenario_clusters.json`` under
tmp_path; each registry uses project_root=tmp_path so the usage funnel writes
under the fixture, not the real repo.

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


def _make_skill(d: Path, name: str, desc: str, theme: str = "universal") -> None:
    """Write a skill .md. theme="" omits the theme line (mimics a learned skill)."""
    d.mkdir(parents=True, exist_ok=True)
    theme_line = f"theme: {theme}\n" if theme else ""
    (d / f"{name}.md").write_text(
        f"---\n{theme_line}name: {name}\ndescription: {desc}\n"
        f"tags: [t]\ncreated: 2026-06-16\nupdated: 2026-06-16\n"
        f"---\n\n# {name}\n",
        encoding="utf-8",
    )


def _project(tmp: Path, guides=None, learned=None, clusters=None,
             tiers=None) -> SkillRegistry:
    """Build a fixture project. guides: list of (name, desc, theme);
    learned: list of (name, desc) (learned skills carry no theme)."""
    if guides is None:
        guides = [("alpha-skill", "Alpha does A.", "universal")]
    for name, desc, theme in guides:
        _make_skill(tmp / ".claude" / "skills", name, desc, theme)
    for name, desc in (learned or []):
        _make_skill(tmp / ".claude" / "skills" / "learned", name, desc, theme="")
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    if clusters is not None:
        (sk / "_scenario_clusters.json").write_text(
            json.dumps(clusters), encoding="utf-8")
    if tiers is not None:
        # P-0118: retired central file; may still linger in a mid-migration repo.
        (sk / "_tiers.json").write_text(json.dumps(tiers), encoding="utf-8")
    reg = SkillRegistry(project_root=tmp)
    reg.scan()
    return reg


def test_none_when_nothing_surfaces(tmp_path):
    """Only a core-only guide, no learned, no clusters -> None (counts fallback)."""
    reg = _project(tmp_path, guides=[("solo", "Solo.", "core-only")])
    assert emit_bounded_injection(reg) is None


def test_universal_from_theme(tmp_path):
    """A guide themed `universal` lands in the always-inject pool."""
    reg = _project(tmp_path, guides=[("alpha-skill", "Alpha does A.", "universal")])
    out = emit_bounded_injection(reg)
    assert out is not None
    assert "alpha-skill" in out and "Alpha does A." in out
    assert "Universal" in out


def test_learned_always_universal(tmp_path):
    """Learned skills carry no theme but are always in the universal pool."""
    reg = _project(
        tmp_path,
        guides=[("g", "G.", "core-only")],
        learned=[("beta-skill", "Beta does B.")],
    )
    out = emit_bounded_injection(reg)
    assert out is not None
    assert "beta-skill" in out


def test_core_only_guide_excluded(tmp_path):
    """theme: core-only / <agent> guides are NOT in the every-session pool."""
    reg = _project(tmp_path, guides=[
        ("uni", "Uni.", "universal"),
        ("secret", "Secret.", "core-only"),
    ])
    out = emit_bounded_injection(reg)
    assert "uni" in out
    assert "secret" not in out


def test_tiers_json_ignored(tmp_path):
    """P-0118 regression guard: a lingering _tiers.json must NOT drive injection."""
    reg = _project(
        tmp_path,
        guides=[("uni", "Uni.", "universal")],
        tiers={"tiers": {"universal": {"skills": ["ghost-skill"]}}},
    )
    out = emit_bounded_injection(reg)
    assert "uni" in out
    assert "ghost-skill" not in out  # the central file is retired, not read


def test_cluster_map(tmp_path):
    reg = _project(
        tmp_path,
        guides=[("alpha-skill", "Alpha does A.", "universal")],
        clusters={"clusters": {"release-pipeline": {
            "description": "ship a version",
            "members": ["alpha-skill"]}}},
    )
    out = emit_bounded_injection(reg)
    assert out is not None
    assert "release-pipeline" in out
    assert "ship a version" in out


def test_universal_capped(tmp_path):
    guides = [(f"s{i:02d}", f"desc{i}", "universal")
              for i in range(_UNIVERSAL_INJECTION_LIMIT + 5)]
    reg = _project(tmp_path, guides=guides)
    out = emit_bounded_injection(reg)
    shown = [ln for ln in out.splitlines() if ln.startswith("    s")]
    assert len(shown) <= _UNIVERSAL_INJECTION_LIMIT
    assert "+5 more" in out


def test_bounded_line_ceiling(tmp_path):
    """The menu stays bounded -- NOT the ~55-line full dump C3 removed."""
    reg = _project(
        tmp_path,
        guides=[("alpha-skill", "Alpha does A.", "universal")],
        clusters={"clusters": {"c1": {"members": ["alpha-skill"]}}},
    )
    out = emit_bounded_injection(reg)
    assert len(out.splitlines()) < 40


def test_records_surfaced(tmp_path):
    """Path-A surfacing is recorded on the live emit (revives the funnel arm)."""
    reg = _project(
        tmp_path, guides=[("alpha-skill", "Alpha does A.", "universal")])
    emit_bounded_injection(reg)
    row = reg._get_tracker().funnel_row("alpha-skill")
    assert row["surfaced_count"] >= 1
