"""Unit test for maintainer/curate_gate.py (P-0082 Phase 2, P-0090).

Drives the deterministic auto-promote gate through its fail-closed matrix. The
external-state dependencies (origin-revoked, secret scan, rejected dedup,
trial-apply pytest) are monkeypatched so each branch is exercised offline; the
envelope reconstruction is tested for real against `uplink.build_issue` output.

Key safety invariant under test: every individual check fails CLOSED
(eligible=False), and the happy path is eligible ONLY when all pass.

Run from repo root:
    python tools/test_curate_gate.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "maintainer"))

import curate_gate as cg  # noqa: E402
from governance_core.candidates import uplink as _uplink  # noqa: E402
from governance_core.candidates import registry as _registry  # noqa: E402


def _check(cond: bool, label: str, failed: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}]   {label}")
    if not cond:
        failed.append(label)


def _skill_envelope(parent: Path, *, kind="skill", layer="candidate-common",
                    source_paths=None, payload=None) -> Path:
    """Write a valid candidate envelope (candidate.json + payload) and return it."""
    source_paths = source_paths or ["payload/generic_thing.md"]
    payload = payload if payload is not None else "---\ntitle: t\n---\nbody\n"
    env = parent / "env"
    env.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema": 1, "id": "cand-x-20260602-thing", "kind": kind,
        "origin": "x", "created": "2026-06-02T00:00:00Z", "layer": layer,
        "title": "thing", "rationale": "generic common-layer helper",
        "source_paths": source_paths,
    }
    (env / "candidate.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for rel in source_paths:
        p = env / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    return env


def _body(env: Path) -> str:
    return _uplink.build_issue(env)[1]


class _Patches:
    """Patch the external-state deps to 'passing' so deeper branches are reached."""
    def __enter__(self):
        self._orig = {
            "revoked": _registry.is_consumer_revoked,
            "scan": _uplink.scan_envelope,
            "rejected": cg._is_rejected,
            "trial": cg.trial_apply,
        }
        _registry.is_consumer_revoked = lambda path, cid: False
        _uplink.scan_envelope = lambda env: []
        cg._is_rejected = lambda env, meta: False
        cg.trial_apply = lambda env, meta, root: (True, "green (mocked)")
        return self

    def __exit__(self, *a):
        _registry.is_consumer_revoked = self._orig["revoked"]
        _uplink.scan_envelope = self._orig["scan"]
        cg._is_rejected = self._orig["rejected"]
        cg.trial_apply = self._orig["trial"]


def main() -> int:
    failed: list[str] = []

    # 1. kill-switch ships disabled (fail-closed)
    _check(cg.is_auto_curate_enabled() is False,
           "1. kill-switch ships disabled (advise-only)", failed)

    # 2. reconstruct round-trips against the real build_issue body
    with tempfile.TemporaryDirectory() as tmp:
        env = _skill_envelope(Path(tmp), payload="---\ntitle: x\n---\nhello world\n")
        body = _body(env)
        with tempfile.TemporaryDirectory() as tmp2:
            rec = cg.reconstruct_envelope(body, Path(tmp2))
            ok = rec is not None
            if ok:
                meta = json.loads((rec / "candidate.json").read_text(encoding="utf-8"))
                content = (rec / "payload/generic_thing.md").read_text(encoding="utf-8")
                ok = (meta["id"] == "cand-x-20260602-thing"
                      and "hello world" in content)
            _check(ok, "2. reconstruct_envelope round-trips candidate.json + payload", failed)

    # 3. happy path: clean net-new skill -> eligible (trial mocked green)
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp)))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is True, "3. clean net-new skill -> eligible", failed)

    # 4. kind=hook -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp), kind="hook",
                                     source_paths=["payload/x.py"], payload="print(1)\n"))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "kind" in r.reasons[0],
               "4. kind=hook -> not eligible", failed)

    # 5. layer=business -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp), layer="business"))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "layer" in r.reasons[0],
               "5. layer=business -> not eligible", failed)

    # 6. revoked origin -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        _registry.is_consumer_revoked = lambda path, cid: True
        body = _body(_skill_envelope(Path(tmp)))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "revoked" in r.reasons[0],
               "6. revoked origin -> not eligible", failed)

    # 7. secret found -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        _uplink.scan_envelope = lambda env: ["<finding>"]
        body = _body(_skill_envelope(Path(tmp)))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "secret" in r.reasons[0],
               "7. secret in payload -> not eligible", failed)

    # 8. previously-rejected -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        cg._is_rejected = lambda env, meta: True
        body = _body(_skill_envelope(Path(tmp)))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "rejected" in r.reasons[0],
               "8. previously-rejected -> not eligible", failed)

    # 9. security-surface hit -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp),
                                     source_paths=["payload/hooks_manifest.json"],
                                     payload="{}\n"))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "surface" in r.reasons[0],
               "9. security-surface hit -> not eligible", failed)

    # 10. not net-new (overwrites a tracked file) -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp),
                                     source_paths=["governance_core/__init__.py"],
                                     payload="__version__='x'\n"))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "net-new" in r.reasons[0],
               "10. not net-new -> not eligible", failed)

    # 11. skill theme held (governance) -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        body = _body(_skill_envelope(Path(tmp),
                                     payload="---\ntheme: governance\n---\nx\n"))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "theme" in r.reasons[0],
               "11. skill theme=governance -> not eligible", failed)

    # 12. trial-apply red -> not eligible
    with tempfile.TemporaryDirectory() as tmp, _Patches():
        cg.trial_apply = lambda env, meta, root: (False, "pytest red (rc=1)")
        body = _body(_skill_envelope(Path(tmp)))
        r = cg.evaluate(body, project_root=REPO_ROOT, run_trial=True)
        _check(r.eligible is False and "trial-apply" in r.reasons[0],
               "12. trial-apply red -> not eligible", failed)

    # 13. unreconstructable body -> not eligible
    r = cg.evaluate("no candidate.json here", project_root=REPO_ROOT, run_trial=True)
    _check(r.eligible is False and "reconstruct" in r.reasons[0],
           "13. unreconstructable body -> not eligible", failed)

    # 14. empty / blank body -> not eligible (guard against a failed fetch)
    r = cg.evaluate("   ", project_root=REPO_ROOT, run_trial=True)
    _check(r.eligible is False and "empty" in r.reasons[0],
           "14. empty body -> not eligible (guard)", failed)

    print()
    if failed:
        print(f"[FAIL] {len(failed)} case(s) failed")
        return 1
    print("[PASS] all 14 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
