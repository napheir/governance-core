"""Test harness for `upgrade --dry-run` internals + stale-prune-exempt.

Covers:
  - _pkg_source_path: maps an autonomy-layer relative path back to its
    package-source file (or None for a business path) (P-0073 Phase 2)
  - _drift_diffs: produces a unified diff of a drifted file's current
    content vs the incoming package-source version (P-0073 Phase 2)
  - _prune_stale + STALE_PRUNE_EXEMPT: released paths are skipped, others
    still pruned (P-0075 consumer-protection mechanism)

The end-to-end `governance-core upgrade --dry-run` (no-write, version
delta, drift report) is exercised by the self-hosted dogfood; this harness
unit-tests the building blocks.

Run from any clone:
    python tools/test_upgrade_dry_run.py
"""
import hashlib
import json
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
        "_pkg_source_path: knowledge/operations -> knowledge_governance/operations/",
        lambda: installer._pkg_source_path("knowledge/operations/foo.md")
        == pkg / "knowledge_governance/operations" / "foo.md"))
    results.append(_case(
        "_pkg_source_path: released path no longer maps (P-0075)",
        lambda: installer._pkg_source_path("knowledge/design/foo.md")
        is None))
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


def _prune_exempt_cases() -> list[bool]:
    """STALE_PRUNE_EXEMPT cases (P-0075): released paths survive prune.

    Simulates a consumer that installed 0.5.0/0.6.0 (so its manifest lists
    the three design/agent paths as install-managed). After upgrading to
    0.7.0 the new install set has no source for them, so naive prune would
    delete them; the exempt set must skip them. A non-exempt stale path
    must still be pruned to prove the guard is selective.
    """
    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_prune_exempt_"))
    try:
        # Stage the three released paths + one non-exempt control path.
        exempt_paths = sorted(installer.STALE_PRUNE_EXEMPT)
        control = "tools/old_stale_tool.py"
        all_old = exempt_paths + [control]

        old_entries = []
        for rel in all_old:
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"# old content for {rel}\n", encoding="utf-8")
            old_entries.append({
                "path": rel,
                "baseline_sha256": hashlib.sha256(
                    p.read_bytes()).hexdigest(),
                "source_version": "0.6.0",
                "category": "agent" if rel.endswith(".md")
                else ("tool" if rel.startswith("tools/") else "knowledge"),
            })

        manifest_path = tmp / installer.INSTALLED_FILES_REL
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({
            "schema": 1, "governance_core_version": "0.6.0",
            "generated_at": "2026-05-20T00:00:00Z",
            "files": old_entries,
        }), encoding="utf-8")

        # New install set (0.7.0) -- empty for this slice; the four paths are
        # all stale (no source). Prune must skip the three exempt, kill control.
        pruned = installer._prune_stale(tmp, installed=[], dry_run=False)

        results.append(_case(
            "_prune_stale: exempt path component-catalog.md survives",
            lambda: (tmp / "knowledge/design/component-catalog.md").exists()))
        results.append(_case(
            "_prune_stale: exempt path design-principles.md survives",
            lambda: (tmp / "knowledge/design/design-principles.md").exists()))
        results.append(_case(
            "_prune_stale: exempt agent design-system-owner.md survives",
            lambda: (tmp / ".claude/agents/design-system-owner.md").exists()))
        # gc #24 (P-0091): the released knowledge-rendering tools survive prune.
        results.append(_case(
            "_prune_stale: exempt build_knowledge_dashboard.py survives (gc #24)",
            lambda: (tmp / "tools/build_knowledge_dashboard.py").exists()))
        results.append(_case(
            "_prune_stale: exempt build_autogen_blocks.py survives (gc #24)",
            lambda: (tmp / "tools/build_autogen_blocks.py").exists()))
        results.append(_case(
            "_prune_stale: exempt dashboard.md survives (gc #24)",
            lambda: (tmp / ".claude/commands/dashboard.md").exists()))
        results.append(_case(
            "_prune_stale: non-exempt control path pruned",
            lambda: not (tmp / control).exists() and control in pruned))
        results.append(_case(
            "_prune_stale: pruned list excludes every exempt path",
            lambda: all(e not in pruned for e in exempt_paths)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    """Run the helper groups; exit non-zero on any failure."""
    results = (_pkg_source_cases() + _drift_diff_cases()
               + _prune_exempt_cases())
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} upgrade-dry-run cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
