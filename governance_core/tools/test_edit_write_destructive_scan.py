"""Smoke test for edit-write-guard.py Layer 6 destructive content scan.

Per proposal harden_indirect_attack_paths.md Phase B verification.

Hybrid mode (default):
  - BLOCK list (literal critical) -> exit 2
  - WARN list (variable forms) -> exit 0 + stderr warn + audit log

Modes via agent_rules/destructive_content_mode.txt:
  - absent / hybrid -> default
  - block -> escalate WARN to also block
  - off -> skip Layer 6
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "edit-write-guard.py"
MODE_FILE = REPO_ROOT / "agent_rules" / "destructive_content_mode.txt"


def run_hook(payload, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
    )
    return result.returncode, result.stderr


def make_payload(tool, file_path, content):
    if tool == "Write":
        return {
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": content},
            "transcript_path": "",
        }
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": file_path,
            "old_string": "PLACEHOLDER_OLD",
            "new_string": content,
        },
        "transcript_path": "",
    }


def cleanup_mode_file():
    try:
        MODE_FILE.unlink()
    except FileNotFoundError:
        pass


def _hits(s):
    return "DESTRUCTIVE CONTENT" in s


def main():
    failed = 0
    cleanup_mode_file()  # ensure default hybrid mode

    # Test fixtures: paths inside repo so L1 cross-repo does NOT fire.
    target_py = REPO_ROOT / "tools" / "_destruct_test_target.py"
    target_safe = REPO_ROOT / "tools" / "_safe_test_target.py"
    target_md = REPO_ROOT / "tools" / "_destruct_test_target.md"

    # Build destructive content fixtures via concat so this test file
    # itself does not trip Layer 6 (the patterns appear only after string
    # construction at runtime, not as static literals in source).
    DOT = "."
    SLASH = "/"
    rmtree_dot_git = "import shutil\nshutil.rmtree('" + DOT + "git')\n"
    rmtree_root = "import shutil\nshutil.rmtree('" + SLASH + "')\n"
    rmtree_var = "import shutil\ndef cleanup(d):\n    shutil.rmtree(d)\n"
    subproc_var = 'import subprocess\nsubprocess.run(["rm", "-rf", path])\n'
    subproc_lit = ('import subprocess\nsubprocess.run('
                   '["bash", "-c", "rm -rf ' + SLASH + '"])\n')
    sql_drop = 'cur.execute("DROP TABLE users")\n'
    clean_code = "def add(a, b):\n    return a + b\n"
    md_content = ("# Doc\nuse shutil." + "rmtree('" + DOT
                  + "git') in scripts to clean up\n")

    # ----- Case 1: BLOCK literal rmtree('.git') -----
    rc, err = run_hook(make_payload("Write", str(target_py), rmtree_dot_git))
    if rc == 2 and "literal" in err:
        sys.stdout.write("  [OK]   1. shutil.rmtree('.git') literal -> block\n")
    else:
        sys.stdout.write("  [FAIL] 1. (rc=" + str(rc) + "): " + err[:200] + "\n")
        failed += 1

    # ----- Case 2: BLOCK rmtree('/') literal -----
    rc, err = run_hook(make_payload("Write", str(target_py), rmtree_root))
    if rc == 2:
        sys.stdout.write("  [OK]   2. shutil.rmtree('/') literal -> block\n")
    else:
        sys.stdout.write("  [FAIL] 2. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 3: WARN rmtree(variable) hybrid -> allow + warn -----
    rc, err = run_hook(make_payload("Write", str(target_py), rmtree_var))
    if rc == 0 and "WARN" in err:
        sys.stdout.write("  [OK]   3. shutil.rmtree(var) hybrid -> warn\n")
    else:
        sys.stdout.write("  [FAIL] 3. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 4: WARN subprocess rm -rf variable -----
    rc, err = run_hook(make_payload("Write", str(target_py), subproc_var))
    if rc == 0 and "WARN" in err:
        sys.stdout.write("  [OK]   4. subprocess rm -rf var -> warn\n")
    else:
        sys.stdout.write("  [FAIL] 4. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 5: BLOCK subprocess rm -rf '/' literal -----
    rc, err = run_hook(make_payload("Write", str(target_py), subproc_lit))
    if rc == 2:
        sys.stdout.write("  [OK]   5. subprocess rm -rf / literal -> block\n")
    else:
        sys.stdout.write("  [FAIL] 5. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 6: WARN SQL DDL drop -----
    rc, err = run_hook(make_payload("Write", str(target_py), sql_drop))
    if rc == 0 and "WARN" in err:
        sys.stdout.write("  [OK]   6. SQL DROP TABLE -> warn\n")
    else:
        sys.stdout.write("  [FAIL] 6. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 7: clean script -> allow + no warn -----
    rc, err = run_hook(make_payload("Write", str(target_safe), clean_code))
    if rc == 0 and not _hits(err):
        sys.stdout.write("  [OK]   7. clean script -> allow + no warn\n")
    else:
        sys.stdout.write("  [FAIL] 7. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 8: non-script ext (.md) -> skip scan -----
    rc, err = run_hook(make_payload("Write", str(target_md), md_content))
    if rc == 0 and not _hits(err):
        sys.stdout.write("  [OK]   8. .md ext -> skip scan\n")
    else:
        sys.stdout.write("  [FAIL] 8. (rc=" + str(rc) + ")\n")
        failed += 1

    # ----- Case 9: mode=block escalates WARN to block -----
    try:
        MODE_FILE.write_text("block\n", encoding="utf-8")
        rc, err = run_hook(make_payload("Write", str(target_py), rmtree_var))
        if rc == 2 and "mode=block" in err.lower():
            sys.stdout.write("  [OK]   9. mode=block escalates WARN -> block\n")
        else:
            sys.stdout.write("  [FAIL] 9. (rc=" + str(rc) + ")\n")
            failed += 1
    finally:
        cleanup_mode_file()

    # ----- Case 10: mode=off skips L6 -----
    try:
        MODE_FILE.write_text("off\n", encoding="utf-8")
        rc, err = run_hook(make_payload("Write", str(target_py), rmtree_dot_git))
        if rc == 0 and not _hits(err):
            sys.stdout.write("  [OK]   10. mode=off skips L6\n")
        else:
            sys.stdout.write("  [FAIL] 10. (rc=" + str(rc) + ")\n")
            failed += 1
    finally:
        cleanup_mode_file()

    sys.stdout.write("\n")
    if failed:
        sys.stdout.write("[FAIL] " + str(failed) + " case(s) failed\n")
        return 1
    sys.stdout.write("[PASS] all 10 cases passed\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
