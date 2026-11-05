# -*- coding: utf-8 -*-
"""
tools/audit_hooks.py - Hook infrastructure self-check (v2, P-0130)
------------------------------------------------------------------
For every clone listed in .governance/config.json, verifies:
  1. every hook in the package hook manifest (hooks_manifest.json) exists
     in .claude/hooks/
  2. every manifest hook is registered in .claude/settings.local.json
  3. no duplicate (matcher, command) hook registrations
  4. hook files match the core clone's copy (multi-clone projects)
  5. .claude/settings.json declares no `hooks` / `enabledPlugins` (a file
     holding only the projectRoot boundary anchor is fine)
  6. permission-count sanity

v1 hard-coded the upstream project's five clones and a hook list that no
longer exists in the package (sensi-guard.py, pipeline-check.py), so it only
reported false problems. v2 derives clones from config and the expected hooks
from the same manifest the installer and `governance-core doctor` use.

Usage:
  python tools/audit_hooks.py
  python tools/audit_hooks.py --fix  (copy missing / differing hooks from core)

Exit codes:
  0 = all checks passed
  1 = issues found (see report)
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERMISSION_LIMIT = 40


def load_clones(root: Path) -> dict:
    """Return {agent name: (clone root, is_core)} from root's config."""
    from governance_core.config import load_config
    cfg = load_config(root)
    if len(cfg.agents) == 1:
        return {cfg.agents[0].name: (root, True)}
    return {a.name: (root.parent / a.clone_dir, a.name == cfg.core_agent_name)
            for a in cfg.agents}


def manifest_hook_files() -> list:
    """Hook filenames shipped by the package (installer / doctor source)."""
    from governance_core.installer import _load_hooks_manifest
    return sorted(_load_hooks_manifest())


def _md5(filepath: Path) -> str:
    """MD5 of a file's content with CRLF normalized ("" if absent)."""
    if not filepath.exists():
        return ""
    data = filepath.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.md5(data).hexdigest()


def _load_settings(repo_path: Path, name: str):
    """Return (settings dict | None, error string | None) for a settings file."""
    path = repo_path / ".claude" / name
    if not path.exists():
        return None, None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return None, f"{name} invalid: {exc}"
    if not isinstance(data, dict):
        return None, f"{name} is not a JSON object"
    return data, None


def _hook_entries(settings: dict):
    """Yield (event, matcher, command) for every registered hook."""
    hooks = settings["hooks"] if "hooks" in settings else {}
    for event, groups in hooks.items():
        for group in groups:
            matcher = group["matcher"] if "matcher" in group else ""
            for hook in (group["hooks"] if "hooks" in group else []):
                yield event, matcher, (hook["command"] if "command" in hook else "")


def _check_hook_files(agent: str, repo_path: Path, expected: list) -> list:
    """Check 1: every manifest hook file exists."""
    hooks_dir = repo_path / ".claude" / "hooks"
    if not hooks_dir.exists():
        return [f"[{agent}] .claude/hooks/ directory missing"]
    return [f"[{agent}] Missing hook: {hook}" for hook in expected
            if not (hooks_dir / hook).exists()]


def _check_registrations(agent: str, repo_path: Path, expected: list) -> list:
    """Checks 2, 3, 6: manifest hooks registered, no duplicates, permissions."""
    settings, err = _load_settings(repo_path, "settings.local.json")
    if err:
        return [f"[{agent}] {err}"]
    if settings is None:
        return [f"[{agent}] settings.local.json missing (run governance-core upgrade)"]
    from governance_core.installer import _hook_file_of
    issues = []
    entries = list(_hook_entries(settings))
    registered = {_hook_file_of({"command": cmd}) for _, _, cmd in entries}
    for hook in expected:
        if hook not in registered:
            issues.append(f"[{agent}] Hook not registered in settings.local.json: {hook}")
    seen: dict = {}
    for event, matcher, cmd in entries:
        seen[(event, matcher, cmd)] = seen.get((event, matcher, cmd), 0) + 1
    for (event, matcher, cmd), count in sorted(seen.items()):
        if count > 1:
            name_match = re.search(r"hooks/([\w\-]+)\.py", cmd)
            name = name_match.group(1) if name_match else cmd[:40]
            issues.append(f"[{agent}] Duplicate hook registration: "
                          f"{event}[{matcher or '*'}]:{name} x{count}")
    perms = settings["permissions"] if "permissions" in settings else {}
    allow = perms["allow"] if isinstance(perms, dict) and "allow" in perms else []
    if len(allow) > PERMISSION_LIMIT:
        issues.append(f"[{agent}] Permission bloat: {len(allow)} rules "
                      f"(target: <{PERMISSION_LIMIT})")
    return issues


def _check_hook_versions(agent: str, repo_path: Path, core_path: Path,
                         expected: list) -> list:
    """Check 4: hook files identical to the core clone's copy."""
    issues = []
    for hook in expected:
        core_hash = _md5(core_path / ".claude" / "hooks" / hook)
        agent_hash = _md5(repo_path / ".claude" / "hooks" / hook)
        if core_hash and agent_hash and core_hash != agent_hash:
            issues.append(f"[{agent}] {hook} differs from core "
                          f"(core={core_hash[:8]}, {agent}={agent_hash[:8]})")
    return issues


def _check_legacy_settings_json(agent: str, repo_path: Path) -> list:
    """Check 5: settings.json must not carry hooks / enabledPlugins.

    Claude Code merges settings.json with settings.local.json; hooks there
    run in addition to the canonical ones. A settings.json holding only the
    projectRoot boundary anchor (installer, P-0129) is expected and clean.
    """
    data, err = _load_settings(repo_path, "settings.json")
    if err:
        return [f"[{agent}] {err}"]
    if data is None:
        return []
    issues = []
    if "hooks" in data:
        issues.append(f"[{agent}] settings.json (non-local) declares hooks -- they "
                      f"merge with settings.local.json and run twice; move them")
    if "enabledPlugins" in data:
        issues.append(f"[{agent}] settings.json enables plugins "
                      f"{sorted(data['enabledPlugins'])} -- verify intent")
    return issues


def _fix_from_core(agent: str, repo_path: Path, core_path: Path,
                   expected: list) -> list:
    """Copy missing or differing manifest hooks from the core clone."""
    fixed = []
    src_dir = core_path / ".claude" / "hooks"
    dst_dir = repo_path / ".claude" / "hooks"
    for hook in expected:
        src, dst = src_dir / hook, dst_dir / hook
        if not src.exists():
            continue
        if not dst.exists() or _md5(src) != _md5(dst):
            dst_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            fixed.append(f"[{agent}] Copied {hook} from core")
    return fixed


def main(root: Path = ROOT, argv: list | None = None) -> int:
    """Run the hook infrastructure audit; return the exit code."""
    parser = argparse.ArgumentParser(description="Audit hook infrastructure")
    parser.add_argument("--fix", action="store_true",
                        help="Copy missing/outdated hooks from the core clone")
    args = parser.parse_args(argv)

    clones = load_clones(root)
    expected = manifest_hook_files()
    core_path = next(path for path, is_core in clones.values() if is_core)
    all_issues: list = []

    print("=" * 60)
    print("Hook Infrastructure Audit")
    print("=" * 60)
    print()
    for agent, (repo_path, is_core) in clones.items():
        if not repo_path.exists():
            print(f"[SKIP] {agent}: clone not found at {repo_path}")
            continue
        issues = []
        issues.extend(_check_hook_files(agent, repo_path, expected))
        issues.extend(_check_registrations(agent, repo_path, expected))
        if not is_core:
            issues.extend(_check_hook_versions(agent, repo_path, core_path, expected))
        issues.extend(_check_legacy_settings_json(agent, repo_path))
        if issues:
            all_issues.extend(issues)
            print(f"[WARN] {agent}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"[OK]   {agent}: all checks passed")
        if args.fix and not is_core:
            for fix in _fix_from_core(agent, repo_path, core_path, expected):
                print(f"  [FIX] {fix}")

    print()
    print("-" * 60)
    if all_issues:
        print(f"Total: {len(all_issues)} issue(s) found")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
