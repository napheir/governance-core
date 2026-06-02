"""Test harness for tools/upgrade_review.py (gc #22).

Unit-tests the deterministic core -- parse / classify / load_protected --
against a sample of the real `governance-core upgrade --dry-run` output format
(installer._dry_run_report: "version: X -> Y", "crosses N minor", and
"--- drift diff: <rel> ---" lines). The subprocess run_dryrun() + report-writing
main() are exercised by the self-hosted dogfood, not here.

Run from repo root:
    python tools/test_upgrade_review.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core.tools import upgrade_review as ur


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


# A sample matching installer._dry_run_report's logged format. The drift diff
# body deliberately includes unified-diff '---'/'+++' markers to prove the
# drift regex matches only the header lines, not the diff body.
_SAMPLE = """\
[dry-run] governance-core upgrade preview
[dry-run] version: 0.21.0 -> 0.22.0
[dry-run]   crosses 1 minor version line(s) -- review the contracts
[dry-run] would overwrite 12 install-managed file(s)
[dry-run] 2 install-managed file(s) locally edited (drift):
[dry-run] --- drift diff: .claude/hooks/auth-guard.py ---
--- current/.claude/hooks/auth-guard.py
+++ incoming/.claude/hooks/auth-guard.py
@@ -1,1 +1,1 @@
-old
+new
[dry-run] --- drift diff: tools/proposal_lib.py ---
[dry-run] no files written.
"""


def _parse_cases() -> list[bool]:
    """parse() extracts version delta, cross-minor flag, drift paths."""
    results: list[bool] = []
    info = ur.parse(_SAMPLE)
    results.append(_case(
        "parse: version delta 0.21.0 -> 0.22.0",
        lambda: info["current"] == "0.21.0" and info["incoming"] == "0.22.0"))
    results.append(_case(
        "parse: cross_minor flag set",
        lambda: info["cross_minor"] is True))
    results.append(_case(
        "parse: drift = the two header paths only (not diff-body ---)",
        lambda: info["drift"] == [".claude/hooks/auth-guard.py",
                                  "tools/proposal_lib.py"]))
    results.append(_case(
        "parse: no version line -> current/incoming None",
        lambda: ur.parse("nothing here")["current"] is None))
    return results


def _classify_cases() -> list[bool]:
    """classify() verdict contract: NONE / GREEN / YELLOW / RED."""
    results: list[bool] = []
    results.append(_case(
        "classify: up-to-date -> NONE",
        lambda: ur.classify(
            {"current": "0.22.0", "incoming": "0.22.0",
             "cross_minor": False, "drift": []}, [])[0] == "NONE"))
    results.append(_case(
        "classify: new + zero drift + no cross-minor -> GREEN",
        lambda: ur.classify(
            {"current": "0.21.0", "incoming": "0.22.0",
             "cross_minor": False, "drift": []}, [])[0] == "GREEN"))
    results.append(_case(
        "classify: drift, no protected -> YELLOW",
        lambda: ur.classify(
            {"current": "0.21.0", "incoming": "0.22.0",
             "cross_minor": False, "drift": ["tools/x.py"]}, [])[0]
        == "YELLOW"))
    results.append(_case(
        "classify: drift on protected path -> RED",
        lambda: ur.classify(
            {"current": "0.21.0", "incoming": "0.22.0",
             "cross_minor": False, "drift": ["tools/x.py"]},
            ["tools/x.py"])[0] == "RED"))
    results.append(_case(
        "classify: cross-minor + drift -> RED (breaking + lost edits)",
        lambda: ur.classify(
            {"current": "0.21.0", "incoming": "0.23.0",
             "cross_minor": True, "drift": ["tools/x.py"]}, [])[0] == "RED"))
    results.append(_case(
        "classify: cross-minor, zero drift -> YELLOW (review contracts)",
        lambda: ur.classify(
            {"current": "0.21.0", "incoming": "0.23.0",
             "cross_minor": True, "drift": []}, [])[0] == "YELLOW"))
    return results


def _load_protected_cases() -> list[bool]:
    """load_protected() reads the path list, tolerant of missing/bad files."""
    results: list[bool] = []
    tmp = Path(tempfile.mkdtemp(prefix="gc_ur_prot_"))
    saved = ur.PROTECTED_DRIFT_FILE
    try:
        ur.PROTECTED_DRIFT_FILE = tmp / "protected_drift.json"
        results.append(_case(
            "load_protected: missing file -> empty list",
            lambda: ur.load_protected() == []))
        ur.PROTECTED_DRIFT_FILE.write_text(
            json.dumps({"paths": ["tools/x.py", 7, "a.py"]}),
            encoding="utf-8")
        results.append(_case(
            "load_protected: keeps only string paths",
            lambda: ur.load_protected() == ["tools/x.py", "a.py"]))
        ur.PROTECTED_DRIFT_FILE.write_text("{ not json", encoding="utf-8")
        results.append(_case(
            "load_protected: malformed JSON -> empty list",
            lambda: ur.load_protected() == []))
    finally:
        ur.PROTECTED_DRIFT_FILE = saved
        shutil.rmtree(tmp, ignore_errors=True)
    return results


def main() -> int:
    """Run the case groups; exit non-zero on any failure."""
    results = _parse_cases() + _classify_cases() + _load_protected_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} upgrade-review cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
