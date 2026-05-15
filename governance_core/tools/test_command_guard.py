"""Test harness for command-guard.py.

Drives command-guard.py with each test case via stdin, asserts the
expected exit code (0 = allow, 2 = block).

Per proposals/harden_destructive_command_guard.md sec.3.1:
  - 23 destructive cases must block
  - 9 routine cases must allow

Run from any clone:
    python tools/test_command_guard.py
"""
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "command-guard.py"


def run_guard(command: str) -> int:
    payload = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.returncode, result.stderr


# (command, expected_exit_code, label)
DESTRUCTIVE = [
    ("rm -rf ./", 2, "rm -rf relative-cwd"),
    ("rm -rf ../", 2, "rm -rf parent"),
    ("rm -rf /c/Users/naphe/test", 2, "rm -rf absolute Windows"),
    ("rm -rf $HOME/test", 2, "rm -rf $HOME"),
    ("rm -rf .git", 2, "rm -rf .git literal"),
    ("rm -rf agent-core/.git", 2, "rm -rf nested .git"),
    ("git push origin :master", 2, "git push delete-branch shorthand"),
    ("git push origin --delete master", 2, "git push --delete"),
    ("git push --force-with-lease origin master", 2, "git force-with-lease"),
    ("git filter-branch --tree-filter 'rm -rf x' HEAD", 2, "git filter-branch"),
    ("git branch -D feature/test", 2, "git branch -D"),
    ("git reflog expire --expire=now --all", 2, "git reflog expire"),
    ("drop table users", 2, "lowercase drop table"),
    ("Drop Database x", 2, "title-case drop database"),
    ("truncate logs", 2, "lowercase truncate (literal)"),
    ("delete from positions;", 2, "DELETE FROM regex"),
    (r"del /F /S /Q C:\Users\<user>\test", 2, "Windows del destructive"),
    ('powershell -Command "Remove-Item -Recurse -Force C:\\Users\\naphe\\test"',
     2, "PS5.1 Remove-Item -Recurse -Force"),
    ('pwsh -Command "Remove-Item -Recurse -Force C:\\Users\\naphe\\test"',
     2, "PS7 pwsh Remove-Item -Recurse -Force"),
    ("find . -type f -delete", 2, "find -delete"),
    ("> important.db", 2, "redirect-truncate .db"),
    (": > .env", 2, "no-op > .env"),
    ("dd if=/dev/zero of=/dev/sda", 2, "disk-level dd"),
]

ROUTINE = [
    ("git status", 0, "git status"),
    ("git push origin master", 0, "git push routine"),
    ("git pull", 0, "git pull"),
    ("python -m pytest tests/", 0, "pytest"),
    ("ls -la", 0, "ls"),
    ("rm /tmp/scratch.txt", 0, "rm /tmp/ prefix-allowed"),
    ("rm -f ~/.claude/cache/x.json", 0, "rm cache prefix-allowed"),
    # Note: 'echo "drop table" >> notes.md' is intentionally NOT in the
    # routine pass-list. SQL keywords inside quoted echo args are
    # indistinguishable from executable SQL at the shell layer (e.g.
    # 'echo "DROP DATABASE x" | psql'). We accept this false positive in
    # exchange for catching the latter. See harden_destructive_command_guard.md
    # sec.6 known limitations. Workaround for legitimate doc-writing:
    # use Edit tool (not Bash echo) to add SQL examples to notes.
    ("git log --all --graph", 0, "git log"),
]


def main() -> int:
    if not HOOK.exists():
        print(f"FATAL: hook not found at {HOOK}", file=sys.stderr)
        return 2

    failed = 0
    print(f"=== command-guard.py smoke test ===")
    print(f"Hook: {HOOK.relative_to(REPO_ROOT)}")
    print()

    print(f"Destructive cases (must block, exit 2): {len(DESTRUCTIVE)}")
    for cmd, expected, label in DESTRUCTIVE:
        actual, stderr = run_guard(cmd)
        if actual == expected:
            print(f"  [OK]    {label}")
        else:
            failed += 1
            print(f"  [FAIL]  {label}")
            print(f"          cmd:      {cmd}")
            print(f"          expected: {expected}, got: {actual}")
            print(f"          stderr:   {stderr.strip()[:200]}")

    print()
    print(f"Routine cases (must allow, exit 0): {len(ROUTINE)}")
    for cmd, expected, label in ROUTINE:
        actual, stderr = run_guard(cmd)
        if actual == expected:
            print(f"  [OK]    {label}")
        else:
            failed += 1
            print(f"  [FAIL]  {label}")
            print(f"          cmd:      {cmd}")
            print(f"          expected: {expected}, got: {actual}")
            print(f"          stderr:   {stderr.strip()[:200]}")

    print()
    total = len(DESTRUCTIVE) + len(ROUTINE)
    if failed == 0:
        print(f"[PASS] {total}/{total} cases passed")
        return 0
    else:
        print(f"[FAIL] {failed}/{total} cases failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
