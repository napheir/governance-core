"""Test harness for lease-renewal visibility (P-0074 Phase 2).

Covers:
  - registry.lease_status: every active consumer with days_left on its
    lease; revoked excluded; missing-expiry entries get days_left=None
    and sort last; sorted by days_left ascending
  - registry.expiring_consumers: the within-threshold filter, including
    already-lapsed (negative days_left) leases
  - the renewal-reminder.py SessionStart hook: hub-side -- reports
    expiring leases when maintainer/consumer_registry.json exists, stays
    silent when none expire and when there is no maintainer/ directory

The hook reads only the maintainer registry (no auth-code verification,
no network), so every case here is portable -- no signing key needed.

Run from any clone:
    python tools/test_renewal.py
"""
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import governance_core
from governance_core.candidates import registry


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
    """Return the package-source renewal-reminder.py path."""
    return Path(governance_core.__file__).resolve().parent \
        / "hooks" / "renewal-reminder.py"


_TODAY = datetime.date(2026, 5, 19)


def _consumer(consumer_id: str, expiry, status: str = "active") -> dict:
    """Build a registry consumer entry; expiry None -> no expiry field."""
    entry = {"consumer_id": consumer_id, "status": status,
             "first_issued": "2026-05-19", "last_issued": "2026-05-19",
             "note": "", "recorded_at": "2026-05-19T00:00:00Z"}
    if expiry is not None:
        entry["expiry"] = expiry
    return entry


def _iso(days_from_today: int) -> str:
    """Return an ISO date `days_from_today` away from the fixed test today."""
    return (_TODAY + datetime.timedelta(days=days_from_today)).isoformat()


def _pure_cases() -> list[bool]:
    """lease_status / expiring_consumers unit cases."""
    results: list[bool] = []
    reg = {"schema": 2, "candidates": [], "consumers": [
        _consumer("soon", _iso(10)),          # within window
        _consumer("healthy", _iso(200)),      # outside window
        _consumer("lapsed", _iso(-5)),        # already expired
        _consumer("perpetual", None),         # schema-1 style, no expiry
        _consumer("gone", _iso(3), status="revoked"),  # excluded
    ]}

    rows = registry.lease_status(reg, _TODAY)
    results.append(_case(
        "lease_status excludes revoked consumers",
        lambda: all(r["consumer_id"] != "gone" for r in rows)))
    results.append(_case(
        "lease_status returns the 4 active consumers",
        lambda: len(rows) == 4))
    results.append(_case(
        "lease_status sorts by days_left ascending, None last",
        lambda: [r["consumer_id"] for r in rows]
        == ["lapsed", "soon", "healthy", "perpetual"]))
    results.append(_case(
        "lease_status: lapsed lease has negative days_left",
        lambda: next(r for r in rows
                     if r["consumer_id"] == "lapsed")["days_left"] == -5))
    results.append(_case(
        "lease_status: no-expiry consumer has days_left None",
        lambda: next(r for r in rows
                     if r["consumer_id"] == "perpetual")["days_left"]
        is None))

    expiring = registry.expiring_consumers(reg, _TODAY, 30)
    results.append(_case(
        "expiring_consumers keeps within-threshold + lapsed, drops healthy",
        lambda: sorted(r["consumer_id"] for r in expiring)
        == ["lapsed", "soon"]))
    results.append(_case(
        "expiring_consumers respects a wider threshold",
        lambda: {r["consumer_id"]
                 for r in registry.expiring_consumers(reg, _TODAY, 250)}
        == {"lapsed", "soon", "healthy"}))
    results.append(_case(
        "expiring_consumers excludes a no-expiry consumer at any threshold",
        lambda: all(r["consumer_id"] != "perpetual"
                    for r in registry.expiring_consumers(reg, _TODAY, 9999))))
    return results


def _make_repo(consumers: list[dict] | None) -> tuple[Path, Path]:
    """Build a throwaway repo with the hook; return (root, hook).

    `consumers` None -> no maintainer/ directory at all (consumer project);
    a list -> maintainer/consumer_registry.json with those entries.
    """
    tmp = Path(tempfile.mkdtemp(prefix="gc_renewal_"))
    hook = tmp / ".claude" / "hooks" / "renewal-reminder.py"
    hook.parent.mkdir(parents=True)
    shutil.copy2(_pkg_hook(), hook)
    if consumers is not None:
        reg = tmp / "maintainer" / "consumer_registry.json"
        reg.parent.mkdir(parents=True)
        reg.write_text(json.dumps(
            {"schema": 2, "consumers": consumers, "candidates": []}),
            encoding="utf-8")
    return tmp, hook


def _run_hook(hook: Path) -> str:
    """Run the SessionStart hook as a subprocess; return its stdout."""
    return subprocess.run(
        [sys.executable, str(hook)], input="{}",
        capture_output=True, text=True, timeout=15).stdout


def _hook_cases() -> list[bool]:
    """renewal-reminder.py SessionStart hook cases (real today)."""
    results: list[bool] = []
    today = datetime.date.today()

    def iso(days: int) -> str:
        return (today + datetime.timedelta(days=days)).isoformat()

    # 1. maintainer registry with an expiring lease -> banner
    tmp, hook = _make_repo([_consumer("acme", iso(10))])
    try:
        txt = _run_hook(hook)
        results.append(_case(
            "expiring lease -> [Lease renewal] banner naming the consumer",
            lambda: "[Lease renewal]" in txt and "acme" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. maintainer registry with a lapsed lease -> banner flags 'lapsed'
    tmp, hook = _make_repo([_consumer("stale", iso(-3))])
    try:
        txt = _run_hook(hook)
        results.append(_case(
            "lapsed lease -> banner flags it lapsed",
            lambda: "[Lease renewal]" in txt and "lapsed" in txt))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. maintainer registry, only healthy leases -> silent
    tmp, hook = _make_repo([_consumer("fresh", iso(200))])
    try:
        txt = _run_hook(hook)
        results.append(_case("only healthy leases -> silent",
                             lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4. revoked consumer near expiry -> silent (excluded from lease_status)
    tmp, hook = _make_repo([_consumer("ejected", iso(5), status="revoked")])
    try:
        txt = _run_hook(hook)
        results.append(_case("revoked consumer near expiry -> silent",
                             lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 5. no maintainer/ directory (consumer project) -> silent
    tmp, hook = _make_repo(None)
    try:
        txt = _run_hook(hook)
        results.append(_case("no maintainer/ directory -> silent",
                             lambda: txt.strip() == ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


def main() -> int:
    """Run the pure + hook groups; exit non-zero on any failure."""
    if not _pkg_hook().exists():
        out(f"[FAIL] package hook missing: {_pkg_hook()}")
        return 1
    results = _pure_cases() + _hook_cases()
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} renewal cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
