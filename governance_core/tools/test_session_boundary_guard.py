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


def run_hook_raw(raw: bytes, *, cwd: Path, extra_env: dict | None = None) -> tuple[int, str]:
    """Drive the hook with RAW stdin bytes (bypasses text-mode encoding).

    Used to exercise the UTF-8 byte-decode (#123): the payload is real UTF-8
    bytes (not re-encoded by subprocess text mode), and `extra_env` can force a
    non-UTF-8 stdio locale (PYTHONIOENCODING) so the old text-mode
    `json.load(sys.stdin)` would raise and fail-open — the fixed byte-read must
    still decode + evaluate correctly.
    """
    env = os.environ.copy()
    env.pop("CLAUDE_BOUNDARY_OVERRIDE", None)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw,
        capture_output=True,
        timeout=10,
        cwd=str(cwd),
        env=env,
    )
    return result.returncode, result.stderr.decode("utf-8", errors="replace")


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
        # Device-sink discards (2>/dev/null, >/dev/null, 2>NUL) are OS
        # pseudo-files, never real cross-boundary writes -> must allow (#134;
        # on Windows /dev/null would otherwise resolve to C:/dev/null and block
        # the whole command).
        redirect_pass_cases = [
            (f"cat {inside_target} > {inside_target}.bak",
             "24. cat > inside (redirect in-boundary) -> allow"),
            (f"grep x {inside_target} 2>&1",
             "25. grep ... 2>&1 (fd-dup, not a file write) -> allow"),
            (f"grep x {inside_target} 2>/dev/null",
             "28. grep ... 2>/dev/null (device sink discard) -> allow"),
            (f"cat {inside_target} >/dev/null 2>&1",
             "29. cat >/dev/null 2>&1 (device sink) -> allow"),
            (f"cat {outside_target} 2>/dev/null",
             "30. read outside + 2>/dev/null (sink, no write target) -> allow"),
            ("echo hi 2>NUL",
             "31. echo hi 2>NUL (Windows device sink) -> allow"),
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

        # ----- P-0121 (#135): shape-based tool coverage -----
        # The guard used to gate only {Bash, Edit, Write}; every other
        # write-capable tool (PowerShell, NotebookEdit, ...) bypassed it. It now
        # routes by tool_input SHAPE: a `command` field -> command scan; a
        # WRITE_PATH_TOOLS field -> path check; else fast-exit. Critically, READ
        # tools (Read/Glob/Grep) share file_path/path and must STAY allowed.

        # PowerShell tool: write cmdlets / redirects to an OUTSIDE path -> block.
        ps_block_cases = [
            (f"'data' | Out-File -FilePath {outside_target}",
             "32. PowerShell Out-File outside -> block"),
            (f"Set-Content -Path {outside_target} -Value x",
             "33. PowerShell Set-Content outside -> block"),
            (f"Remove-Item -Recurse -Force {outside_target}",
             "34. PowerShell Remove-Item outside -> block"),
            (f"New-Item -ItemType File -Path {outside_target}",
             "35. PowerShell New-Item -Path outside -> block"),
            (f"Get-Content {inside_target} > {outside_target}",
             "36. PowerShell redirect > outside -> block"),
        ]
        for cmd, label in ps_block_cases:
            rc, err = run_hook(
                {"tool_name": "PowerShell", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            if rc == 2:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}, expected 2): {err.strip()[:200]}")
                failed += 1

        # PowerShell tool: critical path -> block CRITICAL even for a new tool.
        rc, err = run_hook(
            {"tool_name": "PowerShell",
             "tool_input": {"command": f"Set-Content -Path {ssh_path} -Value x"}},
            cwd=agent_core,
        )
        if rc == 2 and "CRITICAL" in err:
            print("  [OK]   37. PowerShell Set-Content ~/.ssh -> block CRITICAL")
        else:
            print(f"  [FAIL] 37. PowerShell critical (rc={rc}): {err.strip()[:200]}")
            failed += 1

        # PowerShell tool: in-boundary write + device sinks ($null / NUL) -> allow.
        ps_pass_cases = [
            (f"'data' | Out-File -FilePath {inside_target}",
             "38. PowerShell Out-File inside -> allow"),
            (f"Get-Content {inside_target} > $null",
             "39. PowerShell > $null (device sink) -> allow"),
            (f"Get-ChildItem {outside_target} 2>$null",
             "40. PowerShell read outside + 2>$null (sink) -> allow"),
            ("Write-Output hi 2>NUL",
             "41. PowerShell 2>NUL (Windows sink) -> allow"),
        ]
        for cmd, label in ps_pass_cases:
            rc, err = run_hook(
                {"tool_name": "PowerShell", "tool_input": {"command": cmd}},
                cwd=agent_core,
            )
            if rc == 0:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}, expected 0): {err.strip()[:200]}")
                failed += 1

        # NotebookEdit: notebook_path outside -> block; inside -> allow.
        rc, err = run_hook(
            {"tool_name": "NotebookEdit",
             "tool_input": {"notebook_path": str(elsewhere / "nb.ipynb")}},
            cwd=agent_core,
        )
        if rc == 2:
            print("  [OK]   42. NotebookEdit notebook_path outside -> block")
        else:
            print(f"  [FAIL] 42. NotebookEdit outside (rc={rc}, expected 2): {err.strip()[:200]}")
            failed += 1
        rc, err = run_hook(
            {"tool_name": "NotebookEdit",
             "tool_input": {"notebook_path": str(agent_core / "nb.ipynb")}},
            cwd=agent_core,
        )
        if rc == 0:
            print("  [OK]   43. NotebookEdit notebook_path inside -> allow")
        else:
            print(f"  [FAIL] 43. NotebookEdit inside (rc={rc}, expected 0): {err.strip()[:200]}")
            failed += 1

        # READ tools must NOT be gated even for an OUTSIDE path: file_path/path
        # are shared with writers, but the guard blocks writes only. Regression
        # guard for the shape-based routing -- it must not block cross-boundary
        # reads (the reason path tools use an explicit writer set, not shape).
        read_allow_cases = [
            ({"tool_name": "Read", "tool_input": {"file_path": str(outside_file)}},
             "44. Read file_path outside -> allow (read not gated)"),
            ({"tool_name": "Glob", "tool_input": {"pattern": "*", "path": str(elsewhere)}},
             "45. Glob path outside -> allow (read not gated)"),
            ({"tool_name": "Grep", "tool_input": {"pattern": "x", "path": str(elsewhere)}},
             "46. Grep path outside -> allow (read not gated)"),
        ]
        for payload, label in read_allow_cases:
            rc, err = run_hook(payload, cwd=agent_core)
            if rc == 0:
                print(f"  [OK]   {label}")
            else:
                print(f"  [FAIL] {label} (rc={rc}, expected 0): {err.strip()[:200]}")
                failed += 1

        # ----- Case 26: CJK path outside boundary under non-UTF-8 stdio -----
        # #123 regression: payload carries a real UTF-8 CJK filename outside the
        # boundary, driven with PYTHONIOENCODING=ascii. The fixed byte-read
        # decodes it and BLOCKS; the old text-mode json.load(sys.stdin) would
        # raise on the CJK bytes under ascii stdio and fail OPEN (exit 0).
        cjk_outside = elsewhere / "中文-secret.txt"
        raw = json.dumps(
            {"tool_name": "Edit",
             "tool_input": {"file_path": str(cjk_outside)}},
            ensure_ascii=False,
        ).encode("utf-8")
        rc, err = run_hook_raw(
            raw, cwd=agent_core, extra_env={"PYTHONIOENCODING": "ascii"})
        if rc == 2:
            print("  [OK]   26. CJK path outside boundary (ascii stdio) -> block")
        else:
            print(f"  [FAIL] 26. CJK outside under ascii stdio (rc={rc}, expected 2): {err.strip()[:200]}")
            failed += 1

        # ----- Case 27: malformed payload -> fail CLOSED (#123) -----
        rc, err = run_hook_raw(b"this is not json{", cwd=agent_core)
        if rc == 2 and "failing closed" in err:
            print("  [OK]   27. malformed payload -> block (fail-closed)")
        else:
            print(f"  [FAIL] 27. malformed payload (rc={rc}, expected 2 + fail-closed): {err.strip()[:200]}")
            failed += 1

    print()
    if failed:
        print(f"[FAIL] {failed} case(s) failed")
        return 1
    print("[PASS] all 46 cases passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
