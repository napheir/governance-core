"""Claude Code SessionStart hook: update-reminder.py

Surfaces an available governance-core update at session start (P-0073
Phase 1). The autonomy layer records the version it was materialized from
(`installed_files.json` -> `governance_core_version`); this hook compares
it to the latest version on PyPI and, when a newer one exists, prints the
update command in the startup banner -- so an owner is never left unaware
that the hub has moved on.

The PyPI query is TTL-cached in the OS temp dir. An unreachable PyPI, a
missing manifest, or any error -> silent exit 0 (a SessionStart hook must
never break a session start). The hub project (governance-core itself) is
an editable install, always current -> silent.
"""
import datetime
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace")

_PYPI_URL = "https://pypi.org/pypi/governance-core/json"
_FETCH_TIMEOUT_SECONDS = 6
# Update availability changes slowly -- one PyPI query per this window is
# plenty, and keeps session start off the network the rest of the time.
_CHECK_TTL = datetime.timedelta(hours=12)
# Cap the optional drift pre-pass: a dry-run copies trees to temp + diffs, so
# bound it so a slow run never delays session start (falls back to no verdict).
_REVIEW_TIMEOUT_SECONDS = 25
_VERDICTS = ("NONE", "GREEN", "YELLOW", "RED")


def _latest_on_pypi(cache_path: Path) -> str | None:
    """Return the latest governance-core version on PyPI (TTL-cached).

    Returns the version string, or None on any failure -- a missing cache
    plus an unreachable PyPI yields None, which the caller treats as
    "say nothing".
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        checked = datetime.datetime.fromisoformat(
            cached["checked_at"].replace("Z", "+00:00"))
        if now - checked < _CHECK_TTL:
            return cached["latest"]
    except Exception:  # noqa: BLE001 - no/stale/unreadable cache -> fetch
        pass
    try:
        with urllib.request.urlopen(
                _PYPI_URL, timeout=_FETCH_TIMEOUT_SECONDS) as resp:
            latest = json.loads(resp.read().decode("utf-8"))["info"]["version"]
    except Exception:  # noqa: BLE001 - PyPI unreachable -> no notification
        return None
    try:
        cache_path.write_text(
            json.dumps({"checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "latest": latest}), encoding="utf-8")
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass
    return latest


def _drift_verdict(root: Path) -> str | None:
    """Best-effort: run the upgrade-review tool, return its verdict or None.

    Spawns ``tools/upgrade_review.py`` (read-only dry-run + mechanical drift
    classification). Only called once a newer version is already known to be
    available, so the dry-run cost is paid rarely. A missing tool, a timeout,
    or any error -> None: the caller falls back to the plain banner. Never
    raises -- a SessionStart hook must never break a session start.
    """
    tool = root / "tools" / "upgrade_review.py"
    if not tool.is_file():
        return None
    try:
        r = subprocess.run(
            [sys.executable, str(tool)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_REVIEW_TIMEOUT_SECONDS, cwd=str(root))
    except Exception:  # noqa: BLE001 - timeout / OS error -> no verdict line
        return None
    lines = (r.stdout or "").strip().splitlines()
    last = lines[-1].strip() if lines else ""
    return last if last in _VERDICTS else None


def _verdict_line(verdict: str | None) -> str:
    """Map an upgrade-review verdict to a banner suffix line (or empty)."""
    if verdict == "GREEN":
        return "  drift review: GREEN -- no local drift; safe to /upgrade.\n"
    if verdict == "YELLOW":
        return ("  drift review: YELLOW -- local edits would be reverted or a "
                "minor line crossed; check audit/upgrade_review/ before "
                "/upgrade.\n")
    if verdict == "RED":
        return ("  drift review: RED -- upgrade would revert a protected local "
                "fix (or cross a minor line with drift); review carefully "
                "before /upgrade.\n")
    return ""  # NONE / None -> no extra line


def main() -> None:
    """Print an update-available banner at session start, if applicable."""
    try:
        json.loads(sys.stdin.read())
    except Exception:  # noqa: BLE001
        pass

    # repo root: hook lives at <repo>/.claude/hooks/update-reminder.py
    root = Path(__file__).resolve().parent.parent.parent
    try:
        cfg = json.loads((root / ".governance" / "config.json")
                         .read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no config -> nothing to say
        sys.exit(0)

    # Hub gate: governance-core itself is an editable install, always
    # current -- a PyPI "update available" check is meaningless for it.
    auth = cfg["authorization"] if "authorization" in cfg else {}
    if isinstance(auth, dict) and "consumer_id" in auth \
            and auth["consumer_id"] == "governance-core":
        sys.exit(0)

    try:
        manifest = json.loads(
            (root / ".governance" / "installed_files.json")
            .read_text(encoding="utf-8"))
        installed = manifest["governance_core_version"]
    except Exception:  # noqa: BLE001 - no manifest -> nothing to compare
        sys.exit(0)

    tag = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    latest = _latest_on_pypi(Path(tempfile.gettempdir()) / f"gc_update_{tag}.json")
    if latest is None:
        sys.exit(0)

    try:
        from governance_core import version_util
    except Exception:  # noqa: BLE001
        sys.exit(0)
    if not version_util.is_newer(latest, installed):
        sys.exit(0)

    msg = (
        f"[governance-core] update available: {latest} "
        f"(this project is on {installed}).\n"
        "  Update: pip install -U governance-core, then run /upgrade "
        "(preview -> review -> apply).\n")
    msg += _verdict_line(_drift_verdict(root))
    sys.stdout.write(msg)
    sys.exit(0)


if __name__ == "__main__":
    main()
