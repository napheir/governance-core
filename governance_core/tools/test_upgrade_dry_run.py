"""Test harness for `upgrade --dry-run` internals (P-0073 Phase 2).

Covers the two new pure-ish installer helpers:
  - _pkg_source_path: maps an autonomy-layer relative path back to its
    package-source file (or None for a business path)
  - _drift_diffs: produces a unified diff of a drifted file's current
    content vs the incoming package-source version

The end-to-end `governance-core upgrade --dry-run` (no-write, version
delta, drift report) is exercised by the self-hosted dogfood in the
P-0073 Phase 2 validation; this harness unit-tests the building blocks.

Run from any clone:
    python tools/test_upgrade_dry_run.py
"""
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core import installer


def out(line: str) -> None:
    """Write `line` + newline to stdout (constitution Art.7: no print)."""
    sys.stdout.write(line + "\n")


def _case(label: str, fn) -> bool:
    """Run `fn`; return True iff it returns True without raising."""
    try:
        ok = fn()
    except Exception as exc:  # noqa: BLE001
        out(f"[FAIL] {label}: unexpected {type(exc).__name__}: {exc}")
        return False
    out((f"[OK]   {label}") if ok else f"[FAIL] {label}")
    return bool(ok)


def _pkg_source_cases() -> list[bool]:
    """_pkg_source_path mapping cases."""
    pkg = installer.PKG_ROOT
    results: list[bool] = []
    results.append(_case(
        "_pkg_source_path: hook -> governance_core/hooks/",
        lambda: installer._pkg_source_path(".claude/hooks/auth-guard.py")
        == pkg / "hooks" / "auth-guard.py"))
    results.append(_case(
        "_pkg_source_path: tool -> governance_core/tools/",
        lambda: installer._pkg_source_path("tools/proposal_lib.py")
        == pkg / "tools" / "proposal_lib.py"))
    results.append(_case(
        "_pkg_source_path: clause -> governance_core/clauses/",
        lambda: installer._pkg_source_path(
            ".governance/clauses/art_00_ritual.md")
        == pkg / "clauses" / "art_00_ritual.md"))
    results.append(_case(
        "_pkg_source_path: knowledge/design -> knowledge_governance/design/",
        lambda: installer._pkg_source_path("knowledge/design/foo.md")
        == pkg / "knowledge_governance/design" / "foo.md"))
    results.append(_case(
        "_pkg_source_path: business path -> None",
        lambda: installer._pkg_source_path("CLAUDE.md") is None))
    return results


def _drift_diff_cases() -> list[bool]:
    """_drift_diffs cases -- a modified install-managed file yields a diff."""
    results: list[bool] = []
    real = installer.PKG_ROOT / "hooks" / "auth-guard.py"
    tmp = Path(tempfile.mkdtemp(prefix="gc_dryrun_drift_"))
    try:
        rel = ".claude/hooks/auth-guard.py"
        local = tmp / rel
        local.parent.mkdir(parents=True)
        # a locally-edited copy of a real install-managed file
        local.write_text(
            real.read_text(encoding="utf-8") + "\n# local probe edit\n",
            encoding="utf-8")
        diffs = installer._drift_diffs(tmp, [rel])
        results.append(_case(
            "_drift_diffs: returns one entry for the drifted path",
            lambda: len(diffs) == 1 and diffs[0][0] == rel))
        results.append(_case(
            "_drift_diffs: diff is a unified diff carrying the local edit",
            lambda: "# local probe edit" in diffs[0][1]
            and "incoming/" in diffs[0][1]))

        # an unmodified copy -> no textual difference
        local.write_text(real.read_text(encoding="utf-8"), encoding="utf-8")
        same = installer._drift_diffs(tmp, [rel])
        results.append(_case(
            "_drift_diffs: identical content -> no textual difference",
            lambda: "no textual difference" in same[0][1]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    """Run the helper groups; exit non-zero on any failure."""
    results = _pkg_source_cases() + _drift_diff_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} upgrade-dry-run cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
