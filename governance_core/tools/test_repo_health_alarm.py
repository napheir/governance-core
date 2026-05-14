"""Smoke test for Phase C: repo-health alarm + session-boundary-guard gate.

Per proposal harden_indirect_attack_paths.md Phase C verification.

Tests:
  1. Without alarm file: hook passes intra-boundary Bash normally
  2. With alarm file: hook blocks ALL Bash/Edit/Write
  3. Alarm cleared: hook passes again
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "tools" / "session-boundary-guard.py"
ALARM_PATH = Path.home() / ".claude" / "cache" / "repo_health_alarm.json"


def run_hook(payload):
    env = os.environ.copy()
    env.pop("CLAUDE_BOUNDARY_OVERRIDE", None)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(REPO_ROOT),
        env=env,
    )
    return result.returncode, result.stderr


def cleanup_alarm():
    try:
        ALARM_PATH.unlink()
    except FileNotFoundError:
        pass


def main():
    failed = 0
    cleanup_alarm()  # ensure clean state

    # ----- Case 1: no alarm -> intra-boundary Bash passes -----
    rc, err = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
    })
    if rc == 0:
        sys.stdout.write("  [OK]   1. no alarm + git status -> pass\n")
    else:
        sys.stdout.write(f"  [FAIL] 1. (rc={rc}): {err[:200]}\n")
        failed += 1

    # ----- Case 2: alarm set -> all Bash blocked -----
    try:
        ALARM_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALARM_PATH.write_text(json.dumps({
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "repo_root": str(REPO_ROOT),
            "command_preview": "test command that triggered alarm",
            "signals": ["test signal: simulated damage"],
            "cwd": str(REPO_ROOT),
        }), encoding="utf-8")

        rc, err = run_hook({
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        })
        if rc == 2 and "repo-health alarm active" in err:
            sys.stdout.write("  [OK]   2. alarm set + git status -> block\n")
        else:
            sys.stdout.write(f"  [FAIL] 2. (rc={rc}): {err[:200]}\n")
            failed += 1

        # Edit also blocked
        rc, err = run_hook({
            "tool_name": "Edit",
            "tool_input": {"file_path": str(REPO_ROOT / "x.txt")},
        })
        if rc == 2 and "repo-health alarm active" in err:
            sys.stdout.write("  [OK]   3. alarm set + Edit -> block\n")
        else:
            sys.stdout.write(f"  [FAIL] 3. (rc={rc}): {err[:200]}\n")
            failed += 1

        # Write also blocked
        rc, err = run_hook({
            "tool_name": "Write",
            "tool_input": {"file_path": str(REPO_ROOT / "x.txt")},
        })
        if rc == 2 and "repo-health alarm active" in err:
            sys.stdout.write("  [OK]   4. alarm set + Write -> block\n")
        else:
            sys.stdout.write(f"  [FAIL] 4. (rc={rc}): {err[:200]}\n")
            failed += 1
    finally:
        cleanup_alarm()

    # ----- Case 5: alarm cleared -> Bash passes again -----
    rc, err = run_hook({
        "tool_name": "Bash",
        "tool_input": {"command": "git status"},
    })
    if rc == 0:
        sys.stdout.write("  [OK]   5. alarm cleared + Bash -> pass again\n")
    else:
        sys.stdout.write(f"  [FAIL] 5. (rc={rc}): {err[:200]}\n")
        failed += 1

    sys.stdout.write("\n")
    if failed:
        sys.stdout.write(f"[FAIL] {failed} case(s) failed\n")
        return 1
    sys.stdout.write("[PASS] all 5 cases passed\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
