"""Smoke test for tools/derive_session_boundary.py.

Builds synthetic directory layouts under tempdir and asserts each
discovery rule fires correctly.

Cases (per proposals/project_boundary_guard_for_extra_project_writes.md
sec.3.1):
  1. declarative override (.claude/settings.json with projectRoot)
  2. declarative via .claude/settings.local.json (alt file)
  3. git toplevel fallback when no declarative
  4. cwd fallback when no .git and no declarative
  5. nested declarative -- closest wins (deeper override beats higher)
  6. declarative wins over git toplevel even when both present
  7. is_inside_boundary symlink hardening
  8. Windows UNC / drive-root edge: stop walking at filesystem root
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive_session_boundary import (  # noqa: E402
    Boundary,
    derive_boundary,
    is_inside_boundary,
)


def write_settings(d: Path, project_root: str, kind: str = "settings.json") -> None:
    sub = d / ".claude"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / kind).write_text(
        json.dumps({"projectRoot": project_root}),
        encoding="utf-8",
    )


def make_git(d: Path) -> None:
    (d / ".git").mkdir(parents=True, exist_ok=True)


def assert_eq(label: str, got, expected) -> bool:
    if got == expected:
        print(f"  [OK]   {label}")
        return True
    else:
        print(f"  [FAIL] {label}")
        print(f"         expected: {expected}")
        print(f"         got:      {got}")
        return False


def main() -> int:
    failed = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()

        # ---- Case 1: declarative override via settings.json ----
        case1 = tmp_path / "case1"
        case1.mkdir()
        sub1 = case1 / "agent-core"
        sub1.mkdir()
        write_settings(sub1, "../")
        b = derive_boundary(sub1)
        if not assert_eq(
            "1. declarative settings.json projectRoot=../",
            (b.rule, b.path), ("declarative", case1),
        ):
            failed += 1

        # ---- Case 2: declarative via settings.local.json ----
        case2 = tmp_path / "case2"
        case2.mkdir()
        sub2 = case2 / "agent-rules"
        sub2.mkdir()
        write_settings(sub2, "../", kind="settings.local.json")
        b = derive_boundary(sub2)
        if not assert_eq(
            "2. declarative settings.local.json projectRoot=../",
            (b.rule, b.path), ("declarative", case2),
        ):
            failed += 1

        # ---- Case 3: git toplevel fallback ----
        case3 = tmp_path / "case3"
        case3.mkdir()
        make_git(case3)
        sub3 = case3 / "src" / "subdir"
        sub3.mkdir(parents=True)
        b = derive_boundary(sub3)
        if not assert_eq(
            "3. git toplevel fallback (no declarative)",
            (b.rule, b.path), ("git-toplevel", case3),
        ):
            failed += 1

        # ---- Case 4: cwd fallback (no .git, no declarative) ----
        # Build a chain of dirs none of which has .git or .claude.
        case4 = tmp_path / "case4_noroot" / "deep" / "dir"
        case4.mkdir(parents=True)
        b = derive_boundary(case4)
        # Boundary should be case4 itself (since nothing higher matches
        # within tmp_path tree, but tmp_path has no .git either; walking
        # up may eventually hit a .git on the dev box -- so we relax to
        # "rule is cwd OR git-toplevel" depending on outer fs state).
        # Strict check: rule != "declarative".
        if b.rule == "declarative":
            print(f"  [FAIL] 4. cwd-or-git fallback (no declarative)")
            print(f"         got declarative unexpectedly: {b.path}")
            failed += 1
        else:
            print(f"  [OK]   4. cwd-or-git fallback rule={b.rule} (path={b.path})")

        # ---- Case 5: nested declarative -- closest wins ----
        case5 = tmp_path / "case5"
        case5.mkdir()
        write_settings(case5, "/some/outer/scope")  # outer
        sub5 = case5 / "inner"
        sub5.mkdir()
        write_settings(sub5, "../")  # inner (closer)
        b = derive_boundary(sub5)
        if not assert_eq(
            "5. nested declarative -- inner wins",
            (b.rule, b.path), ("declarative", case5),
        ):
            failed += 1

        # ---- Case 6: declarative wins over git toplevel ----
        case6 = tmp_path / "case6"
        case6.mkdir()
        make_git(case6)  # .git here
        sub6 = case6 / "tool"
        sub6.mkdir()
        write_settings(sub6, "/declared/elsewhere")  # declarative wins
        b = derive_boundary(sub6)
        if not assert_eq(
            "6. declarative beats git-toplevel",
            (b.rule, b.path), ("declarative", Path("/declared/elsewhere").resolve()),
        ):
            failed += 1

        # ---- Case 7: is_inside_boundary basic + symlink ----
        case7 = tmp_path / "case7"
        case7.mkdir()
        inside = case7 / "x" / "y.txt"
        inside.parent.mkdir(parents=True)
        inside.write_text("hi", encoding="utf-8")
        outside = tmp_path / "case7_outside" / "z.txt"
        outside.parent.mkdir(parents=True)
        outside.write_text("ho", encoding="utf-8")
        if not assert_eq(
            "7a. inside boundary",
            is_inside_boundary(inside, case7), True,
        ):
            failed += 1
        if not assert_eq(
            "7b. outside boundary",
            is_inside_boundary(outside, case7), False,
        ):
            failed += 1

        # symlink: case7/link -> outside (cannot escape on resolve)
        link = case7 / "link"
        try:
            link.symlink_to(outside.parent)
            # Create-symlink may fail on Windows w/o privilege; skip
            # the assertion if so.
            if link.exists():
                via_link = link / "z.txt"
                if not assert_eq(
                    "7c. symlink does not escape boundary",
                    is_inside_boundary(via_link, case7), False,
                ):
                    failed += 1
            else:
                print("  [SKIP] 7c. symlink (privilege denied on Windows)")
        except (OSError, NotImplementedError):
            print("  [SKIP] 7c. symlink (not supported here)")

        # ---- Case 8: walk stops at filesystem root ----
        # Use a path far enough up that no declarative will be found.
        # On Windows: "C:\" or similar drive root. Just call derive
        # on tmp_path itself; should not raise.
        try:
            b = derive_boundary(tmp_path)
            print(
                f"  [OK]   8. walk terminates at fs root rule={b.rule} "
                f"(no exception)"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL] 8. walk terminates: {exc}")
            failed += 1

    print()
    if failed:
        print(f"[FAIL] {failed} case(s) failed")
        return 1
    print("[PASS] all cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
