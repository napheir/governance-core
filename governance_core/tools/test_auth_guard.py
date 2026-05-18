"""Test harness for auth-guard.py's date-keyed verdict cache (P-0071).

The P-0065 cache stored {code_sha256, pubkey_sha256, valid} with no date,
so a `valid: true` verdict was honored forever -- an expired code kept
being allowed. P-0071 adds `verified_on`: a cached verdict is trusted only
on the day it was written.

This harness drives the real auth-guard.py as a subprocess inside a
throwaway repo tree, pre-seeding the temp-dir cache to assert:
  - a stale (prior-day) `valid: true` verdict is NOT honored -> re-verify
  - a same-day verdict (true or false) IS honored

It uses a deliberately unverifiable code: the test is about cache
freshness, not signature checking (codec signature/expiry is covered by
test_auth_codec.py). A stale `valid: true` that is honored = the bug.

Run from any clone:
    python tools/test_auth_guard.py
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
from governance_core.auth import codec

# A syntactically-shaped GC1 code that does not verify (no real signature).
BAD_CODE = "GC1.eyJzY2hlbWEiOjF9.aaaa"


def _run_hook(hook: Path) -> int:
    """Run `hook` as a PreToolUse subprocess; return its exit code."""
    result = subprocess.run(
        [sys.executable, str(hook)],
        input="{}", capture_output=True, text=True, timeout=15,
    )
    return result.returncode


def main() -> int:
    """Set up a throwaway repo, exercise the cache, report pass/fail."""
    pkg_hook = Path(governance_core.__file__).resolve().parent \
        / "hooks" / "auth-guard.py"
    if not pkg_hook.exists():
        sys.stdout.write(f"[FAIL] package hook missing: {pkg_hook}\n")
        return 1

    tmp_root = Path(tempfile.mkdtemp(prefix="gc_authguard_test_"))
    results: list[bool] = []
    try:
        hook = tmp_root / ".claude" / "hooks" / "auth-guard.py"
        hook.parent.mkdir(parents=True)
        shutil.copy2(pkg_hook, hook)
        cfg = tmp_root / ".governance" / "config.json"
        cfg.parent.mkdir(parents=True)
        cfg.write_text(
            json.dumps({"authorization": {"auth_code": BAD_CODE}}),
            encoding="utf-8")

        root_tag = hashlib.sha256(
            str(tmp_root).encode("utf-8")).hexdigest()[:16]
        cache_path = Path(tempfile.gettempdir()) / f"gc_auth_{root_tag}.json"
        code_sha = hashlib.sha256(BAD_CODE.encode("utf-8")).hexdigest()
        pub_sha = hashlib.sha256(codec.load_bundled_public_key()).hexdigest()
        today = datetime.date.today().isoformat()
        yesterday = (datetime.date.today()
                     - datetime.timedelta(days=1)).isoformat()

        def _seed(verified_on: str, valid: bool) -> None:
            cache_path.write_text(json.dumps({
                "code_sha256": code_sha, "pubkey_sha256": pub_sha,
                "verified_on": verified_on, "valid": valid}), encoding="utf-8")

        def _check(label: str, expect: int) -> bool:
            rc = _run_hook(hook)
            ok = rc == expect
            sys.stdout.write(
                f"{'[OK]  ' if ok else '[FAIL]'} {label} "
                f"(exit {rc}, want {expect})\n")
            return ok

        # 1. No cache: unverifiable code -> block.
        if cache_path.exists():
            cache_path.unlink()
        results.append(_check("no cache -> block", 2))

        # 2. Stale (prior-day) valid:true MUST NOT be honored -> re-verify
        #    -> unverifiable -> block. This is the P-0071 regression guard.
        _seed(yesterday, True)
        results.append(_check("stale valid:true not honored -> block", 2))

        # 3. Same-day valid:true IS honored -> allow (cache optimization).
        _seed(today, True)
        results.append(_check("same-day valid:true honored -> allow", 0))

        # 4. Same-day valid:false IS honored -> block.
        _seed(today, False)
        results.append(_check("same-day valid:false honored -> block", 2))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        try:
            cache_path.unlink()
        except (OSError, NameError):
            pass

    passed = sum(results)
    total = len(results)
    sys.stdout.write(f"\n{passed}/{total} auth-guard cache cases passed\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
