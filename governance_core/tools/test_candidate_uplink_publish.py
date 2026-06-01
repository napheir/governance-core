"""Unit test for uplink.publish_envelope best-effort behavior (P-0088 Phase 2).

publish_envelope must NEVER raise: the issue is already created by the time it
runs, so a release-publish failure (no write access, gh missing, network) must
degrade to a logged no-op returning None. Because uplink_envelope calls it
without a try/except, this is what guarantees a publish failure does not raise
out of uplink_envelope.

Real tarring (shutil.make_archive) runs; only the `gh` subprocess is faked.

Run from repo root:
    python tools/test_candidate_uplink_publish.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from governance_core.candidates import uplink


def _make_envelope(d: Path) -> Path:
    env = d / "env"
    (env / "payload").mkdir(parents=True)
    (env / "candidate.json").write_text(
        json.dumps({"schema": 1, "id": "cand-x-1", "kind": "skill",
                    "origin": "x", "title": "t", "rationale": "r",
                    "source_paths": ["payload/a.txt"]}),
        encoding="utf-8")
    (env / "payload" / "a.txt").write_text("hello", encoding="utf-8")
    return env


def _check(cond: bool, label: str, failed: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}]   {label}")
    if not cond:
        failed.append(label)


def main() -> int:
    failed: list[str] = []
    orig_run = uplink.subprocess.run

    with tempfile.TemporaryDirectory() as tmp:
        env = _make_envelope(Path(tmp))

        # Case 1: gh upload fails (e.g. no write access) -> returns None, no raise
        def run_fail(argv, *a, **k):
            if argv[:3] == ["gh", "release", "upload"]:
                raise subprocess.CalledProcessError(1, argv, stderr="denied")
            return subprocess.CompletedProcess(argv, 0, "", "")
        uplink.subprocess.run = run_fail
        try:
            out = uplink.publish_envelope(env, "cand-x-1", repo="o/r")
            _check(out is None, "1. upload failure -> None (no raise)", failed)
        except Exception as exc:  # noqa: BLE001
            _check(False, f"1. upload failure raised {exc!r}", failed)

        # Case 2: gh not installed -> returns None, no raise
        def run_missing(argv, *a, **k):
            raise FileNotFoundError("gh")
        uplink.subprocess.run = run_missing
        try:
            out = uplink.publish_envelope(env, "cand-x-1", repo="o/r")
            _check(out is None, "2. gh missing -> None (no raise)", failed)
        except Exception as exc:  # noqa: BLE001
            _check(False, f"2. gh missing raised {exc!r}", failed)

        # Case 3: success -> returns the asset name; archive really existed
        seen = {"asset_existed": False}
        def run_ok(argv, *a, **k):
            if argv[:3] == ["gh", "release", "upload"]:
                # the asset path is the second-to-last arg before --clobber
                asset_path = Path(argv[-2])
                seen["asset_existed"] = asset_path.exists()
            return subprocess.CompletedProcess(argv, 0, "", "")
        uplink.subprocess.run = run_ok
        out = uplink.publish_envelope(env, "cand-x-1", repo="o/r")
        _check(out == "cand-x-1.tar.gz", "3. success -> '<id>.tar.gz'", failed)
        _check(seen["asset_existed"], "4. tar.gz archive existed at upload time", failed)

    uplink.subprocess.run = orig_run
    print()
    if failed:
        print(f"[FAIL] {len(failed)} case(s) failed")
        return 1
    print("[PASS] all 4 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
