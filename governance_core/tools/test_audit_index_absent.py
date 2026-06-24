"""Tests for audit graceful-degradation on absent knowledge/INDEX.md (P-0112).

`audit_knowledge.py main()` reads the top `knowledge/INDEX.md` to drive Check 4
(owner-matches-category). A single-agent / pre-index project legitimately has no
top-level INDEX.md, so its absence must:

  - NOT crash with a FileNotFoundError traceback (the validator must tolerate a
    missing optional input), and
  - NOT fail-all (an empty owner map would flag every file's category as
    "unowned") -- instead WARN once and SKIP Check 4, running all other checks.

When INDEX.md IS present, Check 4 behaviour is unchanged (still validates
owner-against-category).

Each fixture builds a synthetic knowledge tree + copies the real frontmatter
contract under tmp_path and drives main(root=tmp_path), fully isolated.

Run from repo root:
    python -m pytest governance_core/tools/test_audit_index_absent.py -q
"""
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # governance_core/tools
import audit_knowledge as ak  # noqa: E402

# Real frontmatter contract: governance_core/contracts/knowledge_frontmatter_schema.md
_CONTRACT_SRC = (
    Path(__file__).resolve().parent.parent
    / "contracts" / "knowledge_frontmatter_schema.md"
)


def _scaffold(tmp: Path, owner: str = "core") -> None:
    """Build a minimal auditable project: contract + one knowledge entry."""
    (tmp / "contracts").mkdir(parents=True, exist_ok=True)
    shutil.copy(_CONTRACT_SRC, tmp / "contracts" / "knowledge_frontmatter_schema.md")
    entry_dir = tmp / "knowledge" / "governance"
    entry_dir.mkdir(parents=True, exist_ok=True)
    (entry_dir / "test-entry.md").write_text(
        f"---\ntitle: Test Entry\nstatus: active\ncreated: 2026-06-24\n"
        f"updated: 2026-06-24\nowner: {owner}\ntags: [governance, test]\n---\n\n"
        f"# Test Entry\n\nBody.\n",
        encoding="utf-8",
    )


def _index(tmp: Path, owner: str) -> None:
    """Write a top knowledge/INDEX.md mapping the `governance` category -> owner."""
    (tmp / "knowledge" / "INDEX.md").write_text(
        "# Knowledge Index\n\n## Subdirectory Overview\n\n"
        "| Subdirectory | Owner | Content |\n"
        "|--------------|-------|---------|\n"
        f"| `governance` | {owner} | governance docs |\n",
        encoding="utf-8",
    )


# ---- parse_category_owner_map: defensive layer ----

def test_parse_map_absent_index_returns_empty(tmp_path):
    (tmp_path / "knowledge").mkdir()
    # No INDEX.md -> empty map, no crash.
    assert ak.parse_category_owner_map(tmp_path / "knowledge") == {}


def test_parse_map_present_index_parses(tmp_path):
    (tmp_path / "knowledge").mkdir()
    _index(tmp_path, "core")
    assert ak.parse_category_owner_map(tmp_path / "knowledge") == {"governance": ["core"]}


# ---- main(): graceful degrade vs unchanged present-path ----

def test_main_absent_index_no_crash_skips_check4(tmp_path, caplog):
    _scaffold(tmp_path, owner="core")  # no INDEX.md
    with caplog.at_level(logging.WARNING):
        rc = ak.main(tmp_path)  # must not raise
    msgs = [r.getMessage() for r in caplog.records]
    # WARN fired, Check 4 skipped (no "not found in top INDEX.md owner map" FAIL)
    assert any("INDEX.md absent" in m for m in msgs)
    assert not any("not found in top INDEX.md owner map" in m for m in msgs)
    assert rc == 0  # entry is otherwise clean -> healthy


def test_main_present_index_match_check4_passes(tmp_path, caplog):
    _scaffold(tmp_path, owner="core")
    _index(tmp_path, "core")  # category governance -> core, matches entry owner
    with caplog.at_level(logging.WARNING):
        rc = ak.main(tmp_path)
    msgs = [r.getMessage() for r in caplog.records]
    assert not any("INDEX.md absent" in m for m in msgs)
    assert not any("not permitted for category" in m for m in msgs)
    assert rc == 0


def test_main_present_index_mismatch_check4_still_fails(tmp_path, caplog):
    # Present-path is UNCHANGED: a real owner/category mismatch must still FAIL.
    _scaffold(tmp_path, owner="core")
    _index(tmp_path, "rules")  # category governance -> rules, but entry owner=core
    with caplog.at_level(logging.WARNING):
        rc = ak.main(tmp_path)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("not permitted for category" in m for m in msgs)
    assert rc == 1
