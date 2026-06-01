"""Smoke test for tools/session-boundary-guard.py.

Drives the hook via stdin (PreToolUse payload schema) under various
synthetic boundaries and asserts allow/block.

Cases (per proposals/project_boundary_guard_for_extra_project_writes.md
sec.3.1 step 5 -- six core scenarios + critical-path coverage):
  1. intra-boundary Edit -> pass
  2. extra-boundary Edit -> block
  3. Bash containing 'cd OUTSIDE && rm Y' -> block
  4. Bash containing 'gh repo create' in cwd outside boundary -> block via cd
  5. CLAUDE_BOUNDARY_OVERRIDE=1 -> pass-through extra-boundary
  6. Critical path (~/.ssh) -> block EVEN with override
  7. Other critical: ~/.claude/settings.json (self-modify guard) -> block
  8. Bash absolute path /c/Windows/... (Windows critical) -> block
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / "tools" / "session-boundary-guard.py"


def run_hook(payload: dict, *, cwd: Path, env_override: bool = False) -> tuple[int, str]:
    env = os.environ.copy()
    # Strip override unless explicitly set, to avoid contaminated tests
    env.pop("CLAUDE_BOUNDARY_OVERRIDE", None)
    if env_override:
        env["CLAUDE_BOUNDARY_OVERRIDE"] = "1"
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
        cwd=str(cwd),
        env=env,
    )
    return result.returncode, result.stderr


def make_settings_json(d: Path, project_root: str) -> None:
    sub = d / ".claude"
    sub.mkdir(parents=True, exist_ok=True)
    (sub / "settings.json").write_text(
        json.dumps({"projectRoot": project_root}),
        encoding="utf-8",
    )


def main() -> int:
    failed = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp).resolve()

        # Layout:
        #   tmp/project/
        #     agent-core/.claude/settings.json (projectRoot=../)
        #   tmp/elsewhere/  (outside boundary)
        project = tmp_path / "project"
        project.mkdir()
        agent_core = project / "agent-core"
        agent_core.mkdir()
        make_settings_json(agent_core, "../")

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        outside_file = elsewhere / "stuff.txt"
        outside_file.write_text("hi", encoding="utf-8")

        # ----- Case 1: intra-boundary Edit -> pass -----
        rc, err = run_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(agent_core / "x.txt")},
            },
            cwd=agent_core,
        )
        if rc == 0:
            print("  [OK]   1. intra-boundary Edit -> pass")
        else:
            print(f"  [FAIL] 1. intra-boundary Edit (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 2: extra-boundary Edit -> block -----
        rc, err = run_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(outside_file)},
            },
            cwd=agent_core,
        )
        if rc == 2:
            print("  [OK]   2. extra-boundary Edit -> block")
        else:
            print(f"  [FAIL] 2. extra-boundary Edit (rc={rc}, expected 2): {err.strip()[:200]}")
            failed += 1

        # ----- Case 3: Bash 'cd OUTSIDE && rm ...' -> block -----
        rc, err = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": f"cd {elsewhere} && rm stuff.txt",
                },
            },
            cwd=agent_core,
        )
        if rc == 2:
            print("  [OK]   3. Bash cd to outside boundary -> block")
        else:
            print(f"  [FAIL] 3. Bash cd-outside (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 4: Bash mkdir at outside path -> block -----
        rc, err = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": f"mkdir -p {tmp_path}/new_outside_repo && cd {tmp_path}/new_outside_repo && git init",
                },
            },
            cwd=agent_core,
        )
        if rc == 2:
            print("  [OK]   4. Bash mkdir-outside -> block")
        else:
            print(f"  [FAIL] 4. Bash mkdir-outside (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 5: override env var -> pass extra-boundary -----
        rc, err = run_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(outside_file)},
            },
            cwd=agent_core,
            env_override=True,
        )
        if rc == 0:
            print("  [OK]   5. CLAUDE_BOUNDARY_OVERRIDE=1 -> pass extra-boundary")
        else:
            print(f"  [FAIL] 5. override-pass (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 6: critical path (.ssh) -> block EVEN with override -----
        # Use a fake .ssh path under tmp; the substring '/.ssh/' triggers
        # critical pattern regardless of where it actually is.
        ssh_path = tmp_path / ".ssh" / "config"
        ssh_path.parent.mkdir(parents=True, exist_ok=True)
        ssh_path.write_text("Host x", encoding="utf-8")
        rc, err = run_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(ssh_path)},
            },
            cwd=agent_core,
            env_override=True,  # even with override
        )
        if rc == 2 and "CRITICAL" in err:
            print("  [OK]   6. critical path (.ssh) blocked even w/ override")
        else:
            print(f"  [FAIL] 6. critical .ssh (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 7: ~/.claude/settings.json self-modify -> block -----
        cc_settings = tmp_path / ".claude" / "settings.json"
        cc_settings.parent.mkdir(parents=True, exist_ok=True)
        cc_settings.write_text("{}", encoding="utf-8")
        rc, err = run_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(cc_settings)},
            },
            cwd=agent_core,
            env_override=True,
        )
        if rc == 2 and "CRITICAL" in err:
            print("  [OK]   7. ~/.claude/settings.json blocked even w/ override")
        else:
            print(f"  [FAIL] 7. settings.json crit (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 8: Windows-style critical path -----
        # Synthesize a /Windows/ path; doesn't have to exist for the test
        # (substring pattern match on resolved-path string).
        win_path = "C:/Windows/System32/important.dll"
        rc, err = run_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": win_path},
            },
            cwd=agent_core,
            env_override=True,
        )
        if rc == 2 and "CRITICAL" in err:
            print("  [OK]   8. /Windows/ system path blocked even w/ override")
        else:
            print(f"  [FAIL] 8. Windows crit (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 9: ~/.claude/projects/.../memory/ -> ALLOW (memory writes) -----
        # This is the key user-data exemption; Memory tool writes here.
        memory_path = (
            Path.home() / ".claude" / "projects" / "C--test--proj"
            / "memory" / "MEMORY.md"
        )
        rc, err = run_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(memory_path)},
            },
            cwd=agent_core,
        )
        if rc == 0:
            print("  [OK]   9. ~/.claude/projects/.../memory -> allow (exempt)")
        else:
            print(f"  [FAIL] 9. memory exempt (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 10: ~/.claude/cache/X.json -> ALLOW (cache writes) -----
        cache_path = Path.home() / ".claude" / "cache" / "test_xyz.json"
        rc, err = run_hook(
            {
                "tool_name": "Write",
                "tool_input": {"file_path": str(cache_path)},
            },
            cwd=agent_core,
        )
        if rc == 0:
            print("  [OK]   10. ~/.claude/cache/X.json -> allow (exempt)")
        else:
            print(f"  [FAIL] 10. cache exempt (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Case 11: ~/.claude/settings.json STILL blocked despite exemption -----
        # Critical-paths check fires before exemption, so settings.json
        # self-modify remains denied.
        settings_path = Path.home() / ".claude" / "settings.json"
        rc, err = run_hook(
            {
                "tool_name": "Edit",
                "tool_input": {"file_path": str(settings_path)},
            },
            cwd=agent_core,
        )
        if rc == 2 and "CRITICAL" in err:
            print("  [OK]   11. ~/.claude/settings.json blocked (critical wins over exempt)")
        else:
            print(f"  [FAIL] 11. settings.json critical-vs-exempt (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # ----- Phase A: indirect-write verbs (sed -i / awk -i inplace / tee /
        # truncate / python -c open / pwsh -OutFile) -----
        outside_target = str(elsewhere / "phaseA_target.txt")
        inside_target = str(agent_core / "phaseA_target.txt")
        Path(inside_target).touch()
        Path(outside_target).touch()

        phase_a_block_cases = [
            (f"sed -i 's/x/y/' {outside_target}",
             "12. sed -i FILE (outside) -> block"),
            (f"awk -i inplace '{{print}}' {outside_target}",
             "13. awk -i inplace FILE (outside) -> block"),
            (f"echo data | tee {outside_target}",
             "14. tee FILE (outside) -> block"),
            (f"truncate -s 0 {outside_target}",
             "15. truncate -s FILE (outside) -> block"),
            (f"python -c \"open('{outside_target}', 'w').write('z')\"",
             "16. python -c open(FILE, w) (outside) -> block"),
            (f"pwsh -Command \"'data' | Out-File -FilePath '{outside_target}'\"",
             "17. pwsh -Command Out-File (outside) -> block"),
        ]
        for cmd, label in phase_a_block_cases:
            rc, err = run_hook(
                {"tool_name": "Bash", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            if rc == 2:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}): {err.strip()[:200]}")
                failed += 1

        # In-boundary should still pass
        phase_a_pass_cases = [
            (f"sed -i 's/x/y/' {inside_target}",
             "18. sed -i (inside boundary) -> allow"),
            (f"echo data | tee {inside_target}",
             "19. tee (inside boundary) -> allow"),
            # Read-only sed (no -i) anywhere -> allow via read-only skip
            (f"sed 's/x/y/' {outside_target}",
             "20. sed (read-only, no -i, even outside) -> allow"),
            (f"awk '{{print}}' {outside_target}",
             "21. awk read-only (no -i inplace, even outside) -> allow"),
        ]
        for cmd, label in phase_a_pass_cases:
            rc, err = run_hook(
                {"tool_name": "Bash", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            if rc == 0:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}): {err.strip()[:200]}")
                failed += 1

        # ----- Redirect-after-read-only-verb regression (2026-05-29) -----
        # A write redirect (> / >>) after a read-only verb (cat/grep/tail)
        # used to be fast-exited as "read-only", bypassing BOTH the boundary
        # check and the critical-path check. is_read_only_bash now returns
        # False whenever a file-write redirect is present.
        redirect_block_cases = [
            (f"cat {inside_target} > {outside_target}",
             "22. cat > outside (redirect after read-only verb) -> block", False),
            (f"cat {inside_target} > {ssh_path}",
             "23. cat > ~/.ssh path (redirect to critical) -> block CRITICAL", True),
        ]
        for cmd, label, want_critical in redirect_block_cases:
            rc, err = run_hook(
                {"tool_name": "Bash", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            crit_ok = ("CRITICAL" in err) if want_critical else True
            if rc == 2 and crit_ok:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}): {err.strip()[:200]}")
                failed += 1

        # fd-dup redirect (2>&1) is not a file write -> must stay read-only;
        # and an in-boundary write redirect after a read-only verb is allowed.
        redirect_pass_cases = [
            (f"cat {inside_target} > {inside_target}.bak",
             "24. cat > inside (redirect in-boundary) -> allow"),
            (f"grep x {inside_target} 2>&1",
             "25. grep ... 2>&1 (fd-dup, not a file write) -> allow"),
        ]
        for cmd, label in redirect_pass_cases:
            rc, err = run_hook(
                {"tool_name": "Bash", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            if rc == 0:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}): {err.strip()[:200]}")
                failed += 1

    print()
    if failed:
        print(f"[FAIL] {failed} case(s) failed")
        return 1
    print("[PASS] all 25 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
