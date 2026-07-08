"""Tests for audit_knowledge Check 11 (per-skill theme) + the learned-surfaced
property of Check 16 (P-0118).

P-0118 retired the central knowledge/skills/_tiers.json and, with it, the whole
family of non-hub catalog carve-outs (gc #101/#102/#114) -- theme lives per-file,
so there is no central synced list to drift or hold phantoms. Check 11 now:

  11a. every command/guide carries a non-empty `theme:` (universal|core-only|<agent>)
  11b. INDEX.md, if generated, matches the builder output

Learned skills carry no theme and are always surfaced. Fixtures drive the audit
with a synthetic .claude/ tree under tmp_path, scanned via project_root=tmp_path.

Run from repo root:
    python -m pytest governance_core/tools/test_skill_theme_audit.py -q
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
        f"created: 2026-06-17\nupdated: 2026-06-17\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _command(tmp: Path, name: str, theme: str = "core-only") -> None:
    d = tmp / ".claude" / "commands"
    d.mkdir(parents=True, exist_ok=True)
    theme_line = f"theme: {theme}\n" if theme else ""
    (d / f"{name}.md").write_text(
        f"---\n{theme_line}name: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-17\nupdated: 2026-06-17\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _learned(tmp: Path, name: str) -> None:
    d = tmp / ".claude" / "skills" / "learned"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: d\ntags: [t]\n"
        f"created: 2026-06-17\nupdated: 2026-06-17\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def _clusters(tmp: Path, data: dict) -> Path:
    sk = tmp / "knowledge" / "skills"
    sk.mkdir(parents=True, exist_ok=True)
    p = sk / "_scenario_clusters.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ---- Check 11: per-skill theme presence ----

def test_ch11_guide_missing_theme_fails(tmp_path):
    _guide(tmp_path, "no-theme-guide", theme="")
    failed, _ = ak._audit_skill_themes(tmp_path)
    assert failed == 1


def test_ch11_command_missing_theme_fails(tmp_path):
    _command(tmp_path, "no-theme-command", theme="")
    failed, _ = ak._audit_skill_themes(tmp_path)
    assert failed == 1


def test_ch11_valid_themes_pass(tmp_path):
    _guide(tmp_path, "uni-guide", theme="universal")
    _command(tmp_path, "core-command", theme="core-only")
    failed, warned = ak._audit_skill_themes(tmp_path)
    assert failed == 0 and warned == 0


def test_ch11_learned_exempt_from_theme(tmp_path):
    # learned skills carry no theme by design -> not a failure.
    _learned(tmp_path, "solo-learned")
    failed, _ = ak._audit_skill_themes(tmp_path)
    assert failed == 0


def test_ch11_index_stale_warns(tmp_path):
    # A present-but-wrong INDEX.md warns (freshness); it does not fail.
    _guide(tmp_path, "uni-guide", theme="universal")
    idx = tmp_path / "knowledge" / "skills" / "INDEX.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    idx.write_text("stale content", encoding="utf-8")
    failed, warned = ak._audit_skill_themes(tmp_path)
    assert failed == 0 and warned == 1


# ---- Check 16: learned always surfaced (replaces the non-hub-learned tolerance) ----

def test_ch16_learned_always_surfaced(tmp_path):
    # Clusters authored, learned skill in none of them -> still surfaced
    # (learned), no FAIL and (unlike the retired non-hub carve-out) no WARN.
    _learned(tmp_path, "pending-skill")
    cp = _clusters(tmp_path, {"clusters": {}})
    failed, warned = ak._audit_scenario_coverage(tmp_path, cp)
    assert failed == 0 and warned == 0
