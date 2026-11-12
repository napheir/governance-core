# -*- coding: utf-8 -*-
"""Check that every business clone is wired the one way (P-0137).

There is one wiring model. `governance-core upgrade --project-root <clone>`
installs gc-managed files into each clone and registers every gc hook
clone-locally (`${CLAUDE_PROJECT_DIR}/.claude/hooks/...`). Tracked project
files reach the clones through the `/sync-repos` merge. This tool no longer
copies or rewires anything. It reads each clone and reports what is off.

Clones are found next to the core clone: `<core clone's parent>/<clone_dir>`,
the same rule as audit_hooks and check_agent_roles. Config `install_root` is
not used: in a nested `<root>/<project>/<clone>` layout it names the
project's parent, and the old copy-and-rewire tool silently skipped every
clone there.

Checks per business clone:
  FAIL clone-missing       the configured clone directory does not exist
  FAIL settings-missing    no readable .claude/settings.local.json
  FAIL foreign-hook-ref    a hook command points outside this clone
  FAIL hook-unregistered   a hook in the clone's hooks_manifest.json is not
                           registered clone-locally
  WARN wide-allow          a wide permissions.allow entry from the
                           destructive-command hardening list is present
  WARN copy-drift          a file in always_copy_files differs from core's
                           (line endings ignored)

Usage:
    python tools/sync_infra.py [--project-root <core clone>] [--agent X] [--json]

Exit codes: 0 = no FAIL, 1 = at least one FAIL, 2 = the check could not run.
`--execute` (the retired copy-and-rewire mode) is refused with exit 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CORE_ROOT = Path(__file__).resolve().parent.parent

# Wide allow entries narrowed by the destructive-command hardening
# (harden_destructive_command_guard §2.5): wide entry -> suggested narrow ones.
WIDE_ALLOW = {
    "Bash(rm:*)": ["Bash(rm /tmp/*)", "Bash(rm -f /tmp/*)",
                   "Bash(rm -f ~/.claude/cache/*)", "Bash(rm -f *.tmp)",
                   "Bash(rm -f *.log)"],
    "Bash(del:*)": ["Bash(del /q *.tmp)"],
    "Bash(powershell:*)": ["Bash(powershell -NoProfile -Command Get-*)",
                           "Bash(powershell -NoProfile -Command Test-Path*)",
                           "Bash(powershell -NoProfile -Command Select-String*)"],
    "Bash(pwsh:*)": ["Bash(pwsh -NoProfile -Command Get-*)",
                     "Bash(pwsh -NoProfile -Command Test-Path*)",
                     "Bash(pwsh -NoProfile -Command Select-String*)"],
}

# Used for the drift WARN when the project has no .governance/sync_files.json
# (P-0059 Phase 2.3b kept this list as the fallback).
FALLBACK_ALWAYS_COPY_FILES = [
    "constitution/total.md",
    ".claude/hooks/edit-write-guard.py",
    ".claude/hooks/scope-guard.py",
    ".claude/hooks/data-source-guard.py",
    ".claude/hooks/_guard_common.py",
    "contracts/__init__.py",
    "contracts/versions.json",
    "knowledge/governance/resource-layer-hardening.md",
]

RETIRED_EXECUTE = ("[FAIL] sync_infra no longer copies or rewires (P-0137). "
                   "Distribute with /sync-repos (tracked files) and "
                   "`governance-core upgrade --project-root <clone>` in each "
                   "clone (gc files and hook wiring); then run this check.")

_PY_PATH = re.compile(r'"([^"]+\.py)"|(\S+\.py)')
_LOCAL_PREFIX = "${CLAUDE_PROJECT_DIR}"


class CheckError(Exception):
    """The check could not run."""


def _out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(core_root: Path) -> dict:
    """The core clone's .governance/config.json."""
    path = core_root / ".governance" / "config.json"
    if not path.is_file():
        raise CheckError(f"no config: {path}")
    try:
        cfg = _read_json(path)
    except ValueError as exc:
        raise CheckError(f"unreadable config {path}: {exc}") from None
    for key in ("agents", "core_agent_name"):
        if not isinstance(cfg, dict) or key not in cfg:
            raise CheckError(f"config {path} lacks `{key}`")
    return cfg


def business_clones(core_root: Path, cfg: dict) -> dict:
    """{agent name: clone path} for every non-core agent, next to the core clone."""
    return {a["name"]: core_root.parent / a["clone_dir"]
            for a in cfg["agents"] if a["name"] != cfg["core_agent_name"]}


def always_copy_files(core_root: Path) -> list:
    """Paths whose core copy each clone should match."""
    path = core_root / ".governance" / "sync_files.json"
    if path.is_file():
        data = _read_json(path)
        if isinstance(data, dict) and "always_copy_files" in data \
                and isinstance(data["always_copy_files"], list):
            return list(data["always_copy_files"])
    return list(FALLBACK_ALWAYS_COPY_FILES)


def hook_script(command: str) -> str | None:
    """The .py path in a hook command, or None."""
    m = _PY_PATH.search(command)
    return (m.group(1) or m.group(2)) if m else None


def _is_local(script: str, clone: Path) -> bool:
    """True when hook script path `script` lies inside `clone`."""
    if script.startswith(_LOCAL_PREFIX):
        return True
    path = Path(script)
    if not path.is_absolute():
        return True
    try:
        path.resolve().relative_to(clone.resolve())
        return True
    except ValueError:
        return False


def _commands(settings: dict) -> list:
    """[(event, command)] for every hook in settings.local.json."""
    hooks = settings["hooks"] if "hooks" in settings else {}
    out = []
    for event, groups in hooks.items():
        for group in groups:
            entries = group["hooks"] if isinstance(group, dict) and "hooks" in group else []
            for h in entries:
                if isinstance(h, dict) and "command" in h:
                    out.append((event, h["command"]))
    return out


def _same_text(a: Path, b: Path) -> bool:
    return a.read_bytes().replace(b"\r\n", b"\n") == b.read_bytes().replace(b"\r\n", b"\n")


def _finding(check: str, level: str, detail: str, fix: str) -> dict:
    return {"check": check, "level": level, "detail": detail, "fix": fix}


def check_clone(core_root: Path, clone: Path, copy_files: list) -> list:
    """Findings for one business clone (read-only)."""
    if not clone.is_dir():
        return [_finding("clone-missing", "FAIL", f"expected clone at {clone}",
                         "fix config agents[].clone_dir, or clone the branch there")]
    upgrade = f"governance-core upgrade --project-root {clone}"
    settings_path = clone / ".claude" / "settings.local.json"
    try:
        settings = _read_json(settings_path)
        if not isinstance(settings, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        return [_finding("settings-missing", "FAIL", f"{settings_path}: {exc}", upgrade)]
    findings = []
    local = set()
    for event, command in _commands(settings):
        script = hook_script(command)
        if script is None:
            continue
        if _is_local(script, clone):
            local.add(script.replace("\\", "/").rsplit("/", 1)[-1])
        else:
            findings.append(_finding(
                "foreign-hook-ref", "FAIL", f"{event}: {command}",
                f"{upgrade}; if the entry survives (a mixed group), remove it "
                "from settings.local.json"))
    manifest_path = clone / ".claude" / "hooks" / "hooks_manifest.json"
    if manifest_path.is_file():
        for name in sorted(_read_json(manifest_path)["hooks"]):
            if name not in local:
                findings.append(_finding("hook-unregistered", "FAIL",
                                         f"{name} is not registered clone-locally",
                                         upgrade))
    perms = settings["permissions"] if "permissions" in settings else {}
    allow = perms["allow"] if isinstance(perms, dict) and "allow" in perms else []
    for wide in sorted(set(allow) & set(WIDE_ALLOW)):
        findings.append(_finding("wide-allow", "WARN", f"permissions.allow has {wide}",
                                 "replace it with: " + ", ".join(WIDE_ALLOW[wide])))
    for rel in copy_files:
        src, dst = core_root / rel, clone / rel
        if src.is_file() and (not dst.is_file() or not _same_text(src, dst)):
            findings.append(_finding("copy-drift", "WARN",
                                     f"{rel} {'is missing' if not dst.is_file() else 'differs from core'}",
                                     f"/sync-repos (merge), then {upgrade}"))
    return findings


def run(core_root: Path, agent: str | None = None) -> dict:
    """{"topology": "single"|"multi", "clones": {name: {"path", "findings"}}}."""
    cfg = load_config(core_root)
    if len(cfg["agents"]) < 2:
        return {"topology": "single", "clones": {}}
    clones = business_clones(core_root, cfg)
    if agent is not None:
        if agent not in clones:
            raise CheckError(f"no business agent {agent!r} in config")
        clones = {agent: clones[agent]}
    copy_files = always_copy_files(core_root)
    return {"topology": "multi",
            "clones": {name: {"path": str(path),
                              "findings": check_clone(core_root, path, copy_files)}
                       for name, path in clones.items()}}


def main(argv: list | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=str(CORE_ROOT),
                        help="the core clone (default: this tool's project)")
    parser.add_argument("--agent", default=None, help="check one business agent")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--execute", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.execute:
        _out(RETIRED_EXECUTE)
        return 2
    try:
        report = run(Path(args.project_root).resolve(), args.agent)
    except (CheckError, OSError, ValueError, KeyError) as exc:
        _out(f"[FAIL] check could not run: {exc}")
        return 2
    fails = sum(1 for c in report["clones"].values()
                for f in c["findings"] if f["level"] == "FAIL")
    if args.json:
        _out(json.dumps(report, ensure_ascii=False, indent=2))
        return 1 if fails else 0
    if report["topology"] == "single":
        _out("[N/A] single-agent topology: no business clones to check")
        return 0
    for name, clone in report["clones"].items():
        _out(f"{name} ({clone['path']})")
        if not clone["findings"]:
            _out("  [OK] wired clone-locally, no drift")
        for f in clone["findings"]:
            _out(f"  [{f['level']}] {f['check']}: {f['detail']}")
            _out(f"         fix: {f['fix']}")
    warns = sum(1 for c in report["clones"].values()
                for f in c["findings"] if f["level"] == "WARN")
    _out(f"Summary: {len(report['clones'])} clone(s), {fails} FAIL, {warns} WARN")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
