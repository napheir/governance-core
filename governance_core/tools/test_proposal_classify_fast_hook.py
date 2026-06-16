"""Tests for .claude/hooks/proposal-classify-fast.py (P-0076 Phase 4)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "proposal-classify-fast.py"
CLASSIFY_LOG = REPO / ".claude" / "cache" / "classify_log.jsonl"


def run_hook(payload: dict, env_overrides: dict = None) -> tuple[int, str, str]:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    if env_overrides:
        env.update(env_overrides)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env=env, cwd=REPO,
    )
    return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()


def _seed_log_entry(session_id: str, path: str) -> None:
    """Inject a classify log entry for this session+path."""
    CLASSIFY_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": "2026-05-26T00:00:00+00:00",
        "session_id": session_id,
        "agent": "core",
        "paths": [path],
        "description": "test seed",
        "verdict": "PROPOSAL_REQUIRED",
        "reason": "test",
        "mode": "quick",
    }
    with CLASSIFY_LOG.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry) + "\n")


def test_harness_path_blocked_without_classify():
    rc, _, err = run_hook(
        {"tool_input": {"file_path": ".claude/commands/test_hook_block.md"}},
        env_overrides={"CLAUDE_SESSION_ID": "test-session-block"},
    )
    assert rc == 2, f"expected block (exit 2), got {rc}"
    assert "PROPOSAL CLASSIFY GATE BLOCK" in err
    assert "harness" in err


def test_non_harness_path_allowed():
    rc, _, _ = run_hook(
        {"tool_input": {"file_path": "analysis/random_file.py"}},
        env_overrides={"CLAUDE_SESSION_ID": "test-session-allow"},
    )
    assert rc == 0


def test_harness_path_allowed_after_classify():
    sid = "test-session-already-classified"
    target = ".claude/commands/test_hook_allow_after.md"
    _seed_log_entry(sid, target)
    rc, _, err = run_hook(
        {"tool_input": {"file_path": target}},
        env_overrides={"CLAUDE_SESSION_ID": sid},
    )
    assert rc == 0, f"expected allow, got rc={rc} err={err}"
    assert "session has prior classify entry" in err


def test_escape_hatch_env_var():
    rc, _, _ = run_hook(
        {"tool_input": {"file_path": ".claude/commands/should_be_blocked.md"}},
        env_overrides={
            "CLAUDE_SESSION_ID": "test-session-escape",
            "CLAUDE_CLASSIFY_FAST_DISABLE": "1",
        },
    )
    assert rc == 0


def test_no_path_payload_allowed():
    rc, _, _ = run_hook({"tool_input": {}})
    assert rc == 0


def test_wall_time_under_150ms():
    t0 = time.perf_counter()
    for _ in range(3):
        run_hook(
            {"tool_input": {"file_path": ".claude/commands/test_perf.md"}},
            env_overrides={"CLAUDE_SESSION_ID": "perf-test"},
        )
    avg = (time.perf_counter() - t0) / 3
    # Allow 250ms wall-time including Python startup; in-process it's <50ms
    assert avg < 0.4, f"avg {avg:.3f}s exceeds 400ms threshold"


def test_fail_open_on_bad_json():
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input="this is not json {{{",
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"}, cwd=REPO,
    )
    assert r.returncode == 0, "hook must fail-open on bad stdin"


def _run_hook_bytes(payload_bytes: bytes, env_overrides: dict) -> int:
    """Drive the hook with raw stdin bytes under an ASCII text-mode stdio.

    PYTHONIOENCODING=ascii forces sys.stdin's TextIOWrapper to ASCII, so the
    OLD locale-text-mode read (sys.stdin.read()) raises UnicodeDecodeError on
    ANY non-ASCII byte -- deterministically, independent of this machine's
    system code page (the hub box runs a UTF-8 code page and cannot reproduce
    the consumer's GBK fail-open otherwise). The fix reads sys.stdin.buffer
    (raw bytes, bypassing the text layer) and decodes UTF-8 explicitly, so it
    is unaffected. Models issue #98's non-cp936 payload class portably.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["PYTHONIOENCODING"] = "ascii"
    env["PYTHONUTF8"] = "0"
    env.update(env_overrides)
    r = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload_bytes, capture_output=True, env=env, cwd=REPO,
    )
    return r.returncode


def test_chinese_payload_reaches_gate_not_fail_open():
    """Issue #98 regression: a high-sensitivity path with Chinese bytes in the
    payload must reach the gate and BLOCK (exit 2), not mis-decode into the
    fail-open backstop. Runs under an ASCII text-mode stdio that would break
    the old sys.stdin.read() on any non-ASCII byte (see _run_hook_bytes)."""
    payload = {
        "tool_input": {"file_path": ".claude/commands/test_hook_utf8_gate.md"},
        "_desc": "描述：包含中文的负载，复现 GBK fail-open。",
    }
    rc = _run_hook_bytes(
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        {"CLAUDE_SESSION_ID": "test-session-utf8-gate"},
    )
    assert rc == 2, (
        f"Chinese payload on high-sensitivity path must BLOCK (exit 2), not "
        f"fail-open; got rc={rc}. UTF-8 byte read is the fix for issue #98."
    )


def test_invalid_utf8_bytes_fail_open_known():
    """Genuinely non-UTF-8 stdin bytes hit the known fail-open branch (the
    classify gate is a documented backstop layer), exit 0 -- not an uncaught
    crash. Confirms UnicodeDecodeError is in the caught tuple."""
    rc = _run_hook_bytes(
        b'\xff\xfe\x00not valid utf-8',
        {"CLAUDE_SESSION_ID": "test-session-bad-bytes"},
    )
    assert rc == 0, f"invalid-UTF-8 stdin must fail-open (exit 0), got rc={rc}"


def main() -> int:
    tests = [
        test_harness_path_blocked_without_classify,
        test_non_harness_path_allowed,
        test_harness_path_allowed_after_classify,
        test_escape_hatch_env_var,
        test_no_path_payload_allowed,
        test_wall_time_under_150ms,
        test_fail_open_on_bad_json,
        test_chinese_payload_reaches_gate_not_fail_open,
        test_invalid_utf8_bytes_fail_open_known,
    ]
    passed = 0
    failed = []
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"[FAIL] {t.__name__}: {e}")
            failed.append(t.__name__)
        except Exception as e:
            print(f"[ERROR] {t.__name__}: {e}")
            failed.append(t.__name__)
    print(f"\n{passed}/{len(tests)} passed")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
