# -*- coding: utf-8 -*-
"""Tests for runtime_import_audit (P-0081, issue #3 root-cause).

Run standalone: python tools/test_runtime_import_audit.py
Exit 0 = all pass, 1 = a failure.
"""
import sys
import tempfile
from pathlib import Path

import governance_core
from governance_core.runtime_import_audit import (
    FAIL_OPEN_GC_IMPORTERS,
    GC_IMPORT_EXEMPT,
    check_runtime_import_discipline,
    hook_imports_gc,
)

_results: list[bool] = []


def _case(label: str, ok: bool) -> None:
    _results.append(ok)
    sys.stdout.write(f"  [{'OK' if ok else 'FAIL'}] {label}\n")


def _synthetic(tmp: Path) -> Path:
    """Build a hooks dir with one of each kind; return it."""
    hooks = tmp / "hooks"
    hooks.mkdir()
    (hooks / "self-contained.py").write_text(
        "import json, sys\nsys.exit(0)\n", encoding="utf-8")
    (hooks / "sensitive-data-guard.py").write_text(  # a known fail-open name
        "import sys\ntry:\n    from governance_core.sensitive_scan import scan_text\n"
        "except Exception:\n    sys.exit(0)\n", encoding="utf-8")
    (hooks / "fail-closed-importer.py").write_text(  # fail-closed gc importer
        "from governance_core.auth import codec\nimport sys\nsys.exit(2)\n",
        encoding="utf-8")
    (hooks / "newcomer.py").write_text(  # unclassified gc importer
        "from governance_core.candidates import registry\nimport sys\n",
        encoding="utf-8")
    return hooks


def main() -> int:
    sys.stdout.write("=== runtime_import_audit ===\n")

    # --- hook_imports_gc ---
    _case("detects `from governance_core.x import y`",
          hook_imports_gc("    from governance_core.auth import codec\n"))
    _case("detects bare `import governance_core`",
          hook_imports_gc("import governance_core\n"))
    _case("ignores a hook with no gc import",
          not hook_imports_gc("import json, sys\nsys.exit(0)\n"))
    _case("does not match a substring like my_governance_core",
          not hook_imports_gc("import my_governance_core_helper\n"))

    # --- check on a synthetic dir ---
    with tempfile.TemporaryDirectory() as td:
        hooks = _synthetic(Path(td))
        names = {"self-contained.py", "sensitive-data-guard.py",
                 "fail-closed-importer.py", "newcomer.py"}
        disc = check_runtime_import_discipline(hooks, names)
        _case("self-contained hook not classified as importer",
              "self-contained.py" not in (disc["fail_open"] + disc["exempt"]
                                          + disc["violations"]))
        _case("fail-open importer -> fail_open",
              disc["fail_open"] == ["sensitive-data-guard.py"])
        _case("no grandfather exemptions remain (P-0082)",
              disc["exempt"] == [])
        _case("every unlisted gc importer -> violation",
              disc["violations"] == ["fail-closed-importer.py", "newcomer.py"])
        # scope: a gc-importing hook NOT in shipped names is ignored
        disc2 = check_runtime_import_discipline(hooks, {"self-contained.py"})
        _case("non-shipped hooks are out of scope",
              disc2["violations"] == [] and disc2["fail_open"] == []
              and disc2["exempt"] == [])

    # --- check against the REAL shipped package hooks ---
    pkg_hooks = Path(governance_core.__file__).resolve().parent / "hooks"
    shipped = {p.name for p in pkg_hooks.glob("*.py")}
    real = check_runtime_import_discipline(pkg_hooks, shipped)
    _case("shipped hooks: NO unclassified violations",
          real["violations"] == [])
    _case("shipped hooks: auth-guard is now self-contained (not an importer)",
          "auth-guard.py" not in (real["fail_open"] + real["exempt"]
                                  + real["violations"]))
    _case("shipped hooks: NO grandfather exceptions remain",
          real["exempt"] == [])
    _case("shipped hooks: every declared fail-open importer is present + imports gc",
          set(real["fail_open"]) == set(FAIL_OPEN_GC_IMPORTERS))
    _case("exempt set is empty (P-0082)",
          set(GC_IMPORT_EXEMPT) == set())

    passed = sum(_results)
    total = len(_results)
    sys.stdout.write(f"\n{passed}/{total} cases passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
