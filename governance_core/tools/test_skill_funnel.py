"""Test harness for the skill-usage funnel (Surfaced/Triggered/Loaded).

Covers the P-0092 (gc #25) mechanism:
  - tracker schema v2 lazy migration + per-day surfaced dedup + per-event
    triggered counting + atomic save (no leftover .tmp, valid JSON)
  - funnel_row zeros for an unrecorded skill
  - router _match_routes fires on_trigger for a dedup-suppressed re-match
    (relevance counted even though the body is not re-injected)
  - registry _emit_funnel classifies retire / slim candidates

tracker + registry are exercised via the editable package import (immediate);
the router is loaded from the autonomy-layer copy, so this harness must run
AFTER `governance-core upgrade --project-root .` ships the new hook.

Run from repo root:
    python tools/test_skill_funnel.py
"""
import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
from pathlib import Path

from governance_core.discovery.tracker import SkillTracker
from governance_core.discovery.registry import SkillRegistry, _emit_funnel

REPO = Path(__file__).resolve().parent.parent
ROUTER = REPO / ".claude" / "hooks" / "prompt-context-router.py"


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


def _fresh_tracker() -> tuple[SkillTracker, Path]:
    """Return a SkillTracker over a fresh temp .usage.json + its parent dir."""
    tmp = Path(tempfile.mkdtemp(prefix="gc_funnel_"))
    return SkillTracker(tracker_path=tmp / ".usage.json"), tmp


def _tracker_cases() -> list[bool]:
    """tracker schema v2 / dedup / atomic-save cases."""
    results: list[bool] = []

    # 1. schema v2 lazy migration: an old 4-key entry gains the new fields on
    #    first record, and the old fields are untouched.
    tr, tmp = _fresh_tracker()
    try:
        tr._data["skills"]["legacy"] = {
            "use_count": 3, "last_used": "2026-01-01",
            "created": "2026-01-01", "refinement_count": 1,
        }
        tr.record_surfaced(["legacy"])
        tr.record_triggered("legacy")
        e = tr._data["skills"]["legacy"]
        results.append(_case(
            "schema v2: new fields added, old fields preserved",
            lambda: e["surfaced_count"] == 1 and e["triggered_count"] == 1
            and e["use_count"] == 3 and e["refinement_count"] == 1))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 2. surfaced per-day dedup: two same-day calls -> count 1; a prior day's
    #    last_surfaced -> next call increments to 2.
    tr, tmp = _fresh_tracker()
    try:
        tr.record_surfaced(["x"])
        tr.record_surfaced(["x"])
        same_day = tr._data["skills"]["x"]["surfaced_count"]
        tr._data["skills"]["x"]["last_surfaced"] = "2000-01-01"
        tr.record_surfaced(["x"])
        next_day = tr._data["skills"]["x"]["surfaced_count"]
        results.append(_case(
            "surfaced: per-day deduped (same-day=1, new-day=2)",
            lambda: same_day == 1 and next_day == 2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. triggered per-event: every call increments (no dedup at this layer).
    tr, tmp = _fresh_tracker()
    try:
        tr.record_triggered("y")
        tr.record_triggered("y")
        results.append(_case(
            "triggered: per-event count increments each call",
            lambda: tr._data["skills"]["y"]["triggered_count"] == 2))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 4. atomic save: no leftover .tmp file, target is valid JSON.
    tr, tmp = _fresh_tracker()
    try:
        tr.record_surfaced(["a", "b"])
        tr.record_triggered("a")
        leftover = list(tmp.glob("*.tmp"))
        parsed = json.loads((tmp / ".usage.json").read_text(encoding="utf-8"))
        results.append(_case(
            "atomic save: no .tmp leftover and target parses as JSON",
            lambda: not leftover and "skills" in parsed))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # 5. funnel_row zeros for an unrecorded skill.
    tr, tmp = _fresh_tracker()
    try:
        row = tr.funnel_row("never-seen")
        results.append(_case(
            "funnel_row: unrecorded skill -> all-zero row",
            lambda: row["surfaced_count"] == 0
            and row["triggered_count"] == 0 and row["use_count"] == 0
            and row["last_triggered"] is None))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return results


class _DummyStream:
    """Stand-in stdout/stderr exposing only a throwaway binary `.buffer`."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()


def _load_router():
    """Load the autonomy-layer router hook as a module (dashed filename).

    At import the hook runs ``sys.stdout = io.TextIOWrapper(sys.stdout.buffer)``
    (and the same for stderr). If it wrapped the real stdout's buffer, that
    wrapper would close the buffer when garbage-collected and corrupt the test
    runner's streams ("I/O operation on closed file"). So feed it throwaway
    buffers during import, then restore the real streams.
    """
    saved_out, saved_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = _DummyStream(), _DummyStream()
        spec = importlib.util.spec_from_file_location("_router_under_test",
                                                       ROUTER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.stdout, sys.stderr = saved_out, saved_err


def _router_cases() -> list[bool]:
    """router _match_routes / _make_trigger_recorder cases."""
    results: list[bool] = []
    if not ROUTER.is_file():
        results.append(_case(
            "router hook present in autonomy layer (run upgrade first)",
            lambda: False))
        return results

    mod = _load_router()
    routes = [{"name": "demo", "triggers": ["data flow"], "path": "x.md"}]

    # dedup-suppressed re-match: route already seen -> excluded from hits, but
    # on_trigger still fires (relevance counted per recurrence).
    fired: list[str] = []
    hits = mod._match_routes("explain the data flow", routes, {"demo"},
                             dedup=True, on_trigger=fired.append)
    results.append(_case(
        "match_routes: seen route excluded from hits but still triggers",
        lambda: hits == [] and fired == ["demo"]))

    # fresh match (not seen): returned as a hit AND triggers.
    fired2: list[str] = []
    hits2 = mod._match_routes("data flow", routes, set(), dedup=True,
                              on_trigger=fired2.append)
    results.append(_case(
        "match_routes: unseen route returned as hit and triggers",
        lambda: len(hits2) == 1 and fired2 == ["demo"]))

    # no match -> no trigger, no hit.
    fired3: list[str] = []
    hits3 = mod._match_routes("unrelated prose", routes, set(),
                              dedup=True, on_trigger=fired3.append)
    results.append(_case(
        "match_routes: non-matching prompt -> no hit, no trigger",
        lambda: hits3 == [] and fired3 == []))

    # recorder is available (tracker importable) -> a callable is returned.
    results.append(_case(
        "make_trigger_recorder: returns a callable when tracker present",
        lambda: callable(mod._make_trigger_recorder())))

    return results


def _funnel_report_cases() -> list[bool]:
    """registry _emit_funnel classification over a seeded temp project."""
    results: list[bool] = []
    proj = Path(tempfile.mkdtemp(prefix="gc_funnel_proj_"))
    try:
        # Three guide skills: one surfaced-only (retire), one triggered-not-
        # loaded (slim), one loaded (neither).
        guide_dir = proj / ".claude" / "skills"
        guide_dir.mkdir(parents=True)
        for name in ("retire-me", "slim-me", "star-me"):
            (guide_dir / f"{name}.md").write_text(
                f"---\ndescription: {name}\n---\nbody\n", encoding="utf-8")

        reg = SkillRegistry(project_root=proj, track_usage=False)
        reg.scan()
        # Inject a temp tracker so seeding/reporting never touches real state.
        usage = proj / ".usage.json"
        reg._tracker = SkillTracker(tracker_path=usage)
        reg._tracker.record_surfaced(["retire-me", "slim-me", "star-me"])
        reg._tracker.record_triggered("slim-me")
        reg._tracker.record_triggered("star-me")
        reg._tracker.record_use("star-me")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _emit_funnel(reg)
        report = buf.getvalue()

        results.append(_case(
            "funnel report: exactly one retire candidate",
            lambda: "retire candidates (surfaced, never triggered/loaded): 1"
            in report))
        results.append(_case(
            "funnel report: exactly one slim candidate",
            lambda: "slim candidates   (triggered, never loaded):          1"
            in report))
        results.append(_case(
            "funnel report: all three skills appear in the table",
            lambda: all(n in report
                        for n in ("retire-me", "slim-me", "star-me"))))
    finally:
        shutil.rmtree(proj, ignore_errors=True)
    return results


def main() -> int:
    """Run the case groups; exit non-zero on any failure."""
    results = (_tracker_cases() + _router_cases() + _funnel_report_cases())
    passed, total = sum(results), len(results)
    out(f"\n{passed}/{total} skill-funnel cases passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
