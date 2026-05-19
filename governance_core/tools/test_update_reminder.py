"""Test harness for the update-available notification (P-0073 Phase 1).

Covers:
  - version_util: parse_version / is_newer / minor_gap
  - the update-reminder.py SessionStart hook: reports an available
    update for a consumer, stays silent when current / hub / no manifest

The hook's PyPI query is TTL-cached; every hook case here pre-seeds a
fresh cache so the test is deterministic and never touches the network.

Run from any clone:
    python tools/test_update_reminder.py
"""
import datetime
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import governance_core
from governance_core import version_util


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


def _pkg_hook() -> Path:
    """Return the package-source update-reminder.py path."""
    return Path(governance_core.__file__).resolve().parent \
        / "hooks" / "update-reminder.py"


def _version_cases() -> list[bool]:
    """version_util unit cases."""
    results: list[bool] = []
    results.append(_case(
        "parse_version: dotted ints -> tuple",
        lambda: version_util.parse_version("0.4.0") == (0, 4, 0)))
    results.append(_case(
        "parse_version: malformed -> None",
        lambda: version_util.parse_version("0.4.x") is None
        and version_util.parse_version(123) is None))
    results.append(_case(
        "is_newer: 0.4.0 > 0.3.0",
        lambda: version_util.is_newer("0.4.0", "0.3.0") is True))
    results.append(_case(
        "is_newer: equal / older / malformed -> False",
        lambda: version_util.is_newer("0.3.0", "0.3.0") is False
        and version_util.is_newer("0.3.0", "0.4.0") is False
        and version_util.is_newer("bad", "0.3.0") is False))
    results.append(_case(
        "minor_gap: 0.5.0 vs 0.3.0 == 2; not-ahead == 0",
        lambda: version_util.minor_gap("0.5.0", "0.3.0") == 2
        and version_util.minor_gap("0.3.0", "0.3.0") == 0))
    return results


def _make_repo(consumer_id: str, manifest_version: str | None,
               cached_latest: str | None) -> tuple[Path, Path]:
    """Build a throwaway repo with the hook + config (+ manifest + cache).

    `manifest_version` None omits installed_files.json; `cached_latest`
    None omits the pre-seeded PyPI cache.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gc_update_reminder_"))
    hook = tmp / ".claude" / "hooks" / "update-reminder.py"
    hook.parent.mkdir(parents=True)
    shutil.copy2(_pkg_hook(), hook)
    cfg = tmp / ".governance" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"authorization": {"consumer_id": consumer_id}}),
                   encoding="utf-8")
    if manifest_version is not None:
        (tmp / ".governance" / "installed_files.json").write_text(
            json.dumps({"schema": 1,
                        "governance_core_version": manifest_version,
                        "generated_at": "2026-05-19T00:00:00Z", "files": []}),
            encoding="utf-8")
    if cached_latest is not None:
        tag = hashlib.sha256(str(tmp).encode("utf-8")).hexdigest()[:16]
        now = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        (Path(tempfile.gettempdir()) / f"gc_update_{tag}.json").write_text(
            json.dumps({"checked_at": now, "latest": cached_latest}),
            encoding="utf-8")
    return tmp, hook


def _cleanup(tmp: Path) -> None:
    """Remove a throwaway repo and its temp-dir PyPI cache."""
    tag = hashlib.sha256(str(tmp).encode("utf-8")).hexdigest()[:16]
    try:
        (Path(tempfile.gettempdir()) / f"gc_update_{tag}.json").unlink()
    except OSError:
        pass
    shutil.rmtree(tmp, ignore_errors=True)


def _run_hook(hook: Path) -> str:
    """Run the SessionStart hook as a subprocess; return its stdout."""
    return subprocess.run(
        [sys.executable, str(hook)], input="{}",
        capture_output=True, text=True, timeout=15).stdout


def _hook_cases() -> list[bool]:
    """update-reminder.py SessionStart hook cases (cache pre-seeded)."""
    results: list[bool] = []

    # 1. consumer, installed 0.4.0, PyPI 9.9.9 -> banner
    tmp, hook = _make_repo("acme", "0.4.0", "9.9.9")
    try:
        txt = _run_hook(hook)
        results.append(_case(
            "consumer + newer on PyPI -> update banner",
            lambda: "[governance-core] update available: 9.9.9" in txt
            and "0.4.0" in txt))
    finally:
        _cleanup(tmp)

    # 2. consumer, installed == latest -> silent
    tmp, hook = _make_repo("acme", "0.4.0", "0.4.0")
    try:
        results.append(_case("consumer + already current -> silent",
                              lambda: _run_hook(hook).strip() == ""))
    finally:
        _cleanup(tmp)

    # 3. hub project -> silent even with a newer version cached
    tmp, hook = _make_repo("governance-core", "0.4.0", "9.9.9")
    try:
        results.append(_case("hub project -> silent",
                              lambda: _run_hook(hook).strip() == ""))
    finally:
        _cleanup(tmp)

    # 4. no installed_files.json -> silent
    tmp, hook = _make_repo("acme", None, "9.9.9")
    try:
        results.append(_case("no manifest -> silent",
                              lambda: _run_hook(hook).strip() == ""))
    finally:
        _cleanup(tmp)

    return results


def main() -> int:
    """Run version_util + hook groups; exit non-zero on any failure."""
    if not _pkg_hook().exists():
        out(f"[FAIL] package hook missing: {_pkg_hook()}")
        return 1
    results = _version_cases() + _hook_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} update-reminder cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
