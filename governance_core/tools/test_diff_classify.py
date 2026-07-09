"""Test harness for diff_classify direction gate (P-0120, issue #132).

Covers:
  - _fm_direction pure logic: ahead / behind / mixed / na
  - classify_knowledge_diff over a real git fixture (base=hub, head=clone):
      * behind : hub has an fm field the clone lacks (removed-only) ->
        M-fm-only + direction 'behind' -> Step 4 MUST skip (else it reverts
        the hub-authored field, the #132 bug)
      * ahead  : clone has an fm field the hub lacks (added-only) ->
        M-fm-only + direction 'ahead' -> collect
      * mixed  : clone changes an fm value (one +, one -) ->
        M-fm-only + direction 'mixed' -> collect
      * body-only change -> M-mixed + direction 'na'
      * added file -> A + direction 'na'
      * deleted file -> D + direction 'na'
  - every record carries a `direction` key (schema uniformity)

Run from repo root (package-source test convention):
    python governance_core/tools/test_diff_classify.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from governance_core.tools.diff_classify import (
    _fm_direction,
    classify_knowledge_diff,
)


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


def _run_git(repo: Path, *args: str) -> None:
    """Run a git command in `repo`, raising on failure (utf-8 decoded)."""
    res = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={res.returncode}): {res.stderr.strip()}"
        )


def _rev_parse(repo: Path, ref: str) -> str:
    """Return the resolved commit hash for `ref`."""
    res = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", ref],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if res.returncode != 0:
        raise RuntimeError(f"git rev-parse {ref} failed: {res.stderr.strip()}")
    return res.stdout.strip()


def _write(repo: Path, rel: str, text: str) -> None:
    """Write `text` to repo/rel as UTF-8 with LF newlines (byte-exact)."""
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(text.encode("utf-8"))


def _remove(repo: Path, rel: str) -> None:
    """Delete repo/rel from the working tree."""
    (repo / rel).unlink()


# --- frontmatter fixtures (base = hub, head = clone) ------------------------

_BEHIND_BASE = "---\nname: behind\nstatus: active\nowner: core\n---\n\n# behind\nstable body\n"
_BEHIND_HEAD = "---\nname: behind\nstatus: active\n---\n\n# behind\nstable body\n"

_AHEAD_BASE = "---\nname: ahead\nstatus: active\n---\n\n# ahead\nstable body\n"
_AHEAD_HEAD = "---\nname: ahead\nstatus: active\ntags: [x]\n---\n\n# ahead\nstable body\n"

_MIXED_BASE = "---\nname: mixed\nstatus: active\n---\n\n# mixed\nstable body\n"
_MIXED_HEAD = "---\nname: mixed\nstatus: draft\n---\n\n# mixed\nstable body\n"

_BODY_BASE = "---\nname: body\nstatus: active\n---\n\n# body\ncontent original\n"
_BODY_HEAD = "---\nname: body\nstatus: active\n---\n\n# body\ncontent modified\n"

_DELETED = "---\nname: deleted\nstatus: active\n---\n\n# deleted\nstable body\n"
_NEW = "---\nname: new\nstatus: active\n---\n\n# new\nstable body\n"


def _fm_direction_cases() -> list[bool]:
    """_fm_direction is a pure function of the two fm counts."""
    return [
        _case("_fm_direction(1,0) -> ahead",
              lambda: _fm_direction(1, 0) == "ahead"),
        _case("_fm_direction(0,1) -> behind",
              lambda: _fm_direction(0, 1) == "behind"),
        _case("_fm_direction(2,3) -> mixed",
              lambda: _fm_direction(2, 3) == "mixed"),
        _case("_fm_direction(0,0) -> na",
              lambda: _fm_direction(0, 0) == "na"),
    ]


def _classify_cases() -> list[bool]:
    """classify_knowledge_diff over a base(hub)->head(clone) git fixture."""
    results: list[bool] = []
    repo = Path(tempfile.mkdtemp(prefix="gc_p120_diffcls_"))
    try:
        _run_git(repo, "init", "-q")
        _run_git(repo, "config", "user.email", "test@example.com")
        _run_git(repo, "config", "user.name", "test")
        # rename detection off so added/deleted files never pair into R.
        _run_git(repo, "config", "diff.renames", "false")

        # --- base commit (hub) ---
        _write(repo, "knowledge/behind.md", _BEHIND_BASE)
        _write(repo, "knowledge/ahead.md", _AHEAD_BASE)
        _write(repo, "knowledge/mixed.md", _MIXED_BASE)
        _write(repo, "knowledge/body.md", _BODY_BASE)
        _write(repo, "knowledge/deleted.md", _DELETED)
        _run_git(repo, "add", "-A")
        _run_git(repo, "commit", "-q", "-m", "base (hub)")
        base = _rev_parse(repo, "HEAD")

        # --- head commit (clone) ---
        _write(repo, "knowledge/behind.md", _BEHIND_HEAD)
        _write(repo, "knowledge/ahead.md", _AHEAD_HEAD)
        _write(repo, "knowledge/mixed.md", _MIXED_HEAD)
        _write(repo, "knowledge/body.md", _BODY_HEAD)
        _remove(repo, "knowledge/deleted.md")
        _write(repo, "knowledge/new.md", _NEW)
        _run_git(repo, "add", "-A")
        _run_git(repo, "commit", "-q", "-m", "head (clone)")
        head = _rev_parse(repo, "HEAD")

        records = classify_knowledge_diff(repo, base, head, ["knowledge/"])
        by_name = {Path(r["path"]).name: r for r in records}

        def status_dir(name: str) -> tuple[str, str]:
            r = by_name[name]
            return r.get("status"), r.get("direction")

        results.append(_case(
            "behind.md: M-fm-only + direction behind (the #132 skip case)",
            lambda: status_dir("behind.md") == ("M-fm-only", "behind")))
        results.append(_case(
            "behind.md: added_in_fm==0, removed_in_fm>0",
            lambda: by_name["behind.md"]["added_in_fm"] == 0
            and by_name["behind.md"]["removed_in_fm"] > 0))
        results.append(_case(
            "ahead.md: M-fm-only + direction ahead (collect)",
            lambda: status_dir("ahead.md") == ("M-fm-only", "ahead")))
        results.append(_case(
            "mixed.md: M-fm-only + direction mixed (collect)",
            lambda: status_dir("mixed.md") == ("M-fm-only", "mixed")))
        results.append(_case(
            "body.md: M-mixed + direction na (body change, not fm)",
            lambda: status_dir("body.md") == ("M-mixed", "na")))
        results.append(_case(
            "new.md: A + direction na",
            lambda: status_dir("new.md") == ("A", "na")))
        results.append(_case(
            "deleted.md: D + direction na",
            lambda: status_dir("deleted.md") == ("D", "na")))
        results.append(_case(
            "every record carries a direction key (schema uniformity)",
            lambda: all("direction" in r for r in records)))
        # The gate the skill applies: collect M-fm-only unless behind.
        results.append(_case(
            "gate: exactly one M-fm-only file is 'behind' (skipped)",
            lambda: sum(
                1 for r in records
                if r.get("status") == "M-fm-only" and r.get("direction") == "behind"
            ) == 1))
    finally:
        shutil.rmtree(repo, ignore_errors=True)
    return results


def main() -> int:
    """Run all groups; exit non-zero on any failure."""
    results = _fm_direction_cases() + _classify_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} diff_classify direction cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
