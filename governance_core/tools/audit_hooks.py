# -*- coding: utf-8 -*-
"""
tools/audit_hooks.py - Hook infrastructure self-check
------------------------------------------------------
Verifies hook consistency across all agent repos:
  1. All expected hook files exist in each repo
  2. Hook registrations in settings.local.json match expected chains
  3. Hook file versions match core (checksum comparison)
  4. Permission count sanity check

Usage:
  python tools/audit_hooks.py
  python tools/audit_hooks.py --fix  (copy missing hooks from core)

Exit codes:
  0 = all checks passed
  1 = issues found (see report)
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT.parent

# Agent repos
AGENTS = {
    "core": BASE / "agent-core",
    "trade": BASE / "agent-trade",
    "rules": BASE / "agent-rules",
    "data": BASE / "agent-data",
    "research": BASE / "agent-research",
}

# Hook files that should exist in every repo. (session-summary.py moved to
# CENTRAL_HOOKS in sync_infra on 2026-04-17 — local copies are no longer
# required; _remove_local_copy prunes them on next sync.)
REQUIRED_HOOKS = [
    "scope-guard.py",
    "sensi-guard.py",
    "edit-write-guard.py",
    "constitutional-review.py",
    "pipeline-check.py",
]

# Hook files unique to core
CORE_ONLY_HOOKS = [
    "command-guard.py",
]

# Hooks that should be identical across repos (synced from core).
# session-summary.py removed 2026-04-17 (now central-reference, not copied).
SYNCED_HOOKS = [
    "sensi-guard.py",
    "constitutional-review.py",
    "pipeline-check.py",
]

# Hook script names that sync_infra registers as central references.
# If a clone's settings.local.json references a local path for any of these,
# _check_stale_local_refs flags it so sync_infra can upgrade on next run.
# Must stay in sync with sync_infra.CENTRAL_HOOKS.
CENTRAL_HOOK_NAMES = {
    "skill-nudge",
    "session-summary",
    "session-context",
    "context-reminder",
    "skill-usage-tracker",
}

# Expected hook stages in settings
EXPECTED_STAGES = ["PreToolUse", "PostToolUse", "Notification"]


def _md5(filepath: Path) -> str:
    """Compute MD5 hash of a file."""
    if not filepath.exists():
        return ""
    return hashlib.md5(filepath.read_bytes()).hexdigest()


def _check_hook_files(agent: str, repo_path: Path) -> list[str]:
    """Check that all required hook files exist."""
    issues = []
    hooks_dir = repo_path / ".claude" / "hooks"

    if not hooks_dir.exists():
        issues.append(f"[{agent}] .claude/hooks/ directory missing")
        return issues

    required = REQUIRED_HOOKS + (CORE_ONLY_HOOKS if agent == "core" else [])
    for hook in required:
        hook_path = hooks_dir / hook
        if not hook_path.exists():
            issues.append(f"[{agent}] Missing hook: {hook}")

    return issues


def _check_hook_versions(agent: str, repo_path: Path) -> list[str]:
    """Check that synced hooks match core's version."""
    if agent == "core":
        return []

    issues = []
    core_hooks = AGENTS["core"] / ".claude" / "hooks"
    agent_hooks = repo_path / ".claude" / "hooks"

    for hook in SYNCED_HOOKS:
        core_hash = _md5(core_hooks / hook)
        agent_hash = _md5(agent_hooks / hook)

        if not core_hash:
            continue  # Core doesn't have it, skip
        if not agent_hash:
            continue  # Already caught by file existence check
        if core_hash != agent_hash:
            issues.append(
                f"[{agent}] {hook} differs from core "
                f"(core={core_hash[:8]}, {agent}={agent_hash[:8]})"
            )

    return issues


def _check_settings(agent: str, repo_path: Path) -> list[str]:
    """Check settings.local.json for expected hook registrations."""
    issues = []
    settings_path = repo_path / ".claude" / "settings.local.json"

    if not settings_path.exists():
        issues.append(f"[{agent}] settings.local.json missing")
        return issues

    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        issues.append(f"[{agent}] settings.local.json invalid: {e}")
        return issues

    hooks = settings.get("hooks", {})

    # Check expected stages exist
    for stage in EXPECTED_STAGES:
        if stage not in hooks:
            issues.append(f"[{agent}] Missing hook stage: {stage}")

    # Check PreToolUse has Bash, Edit, Write matchers
    pre_tool = hooks.get("PreToolUse", [])
    matchers = {entry.get("matcher", "") for entry in pre_tool}
    for expected in ["Bash", "Edit", "Write"]:
        if expected not in matchers:
            issues.append(f"[{agent}] PreToolUse missing matcher: {expected}")

    # Check each hook entry has at least one hook
    for stage_name, stage_entries in hooks.items():
        for entry in stage_entries:
            entry_hooks = entry.get("hooks", [])
            if not entry_hooks:
                matcher = entry.get("matcher", "(empty)")
                issues.append(
                    f"[{agent}] {stage_name}[{matcher}] has no hooks registered"
                )

    # Permission count sanity
    perms = settings.get("permissions", {}).get("allow", [])
    if len(perms) > 40:
        issues.append(
            f"[{agent}] Permission bloat: {len(perms)} rules "
            f"(target: <30)"
        )

    return issues


def _check_duplicate_registrations(agent: str, repo_path: Path) -> list[str]:
    """Flag identical (matcher, command) pairs in settings.local.json hooks.

    sync_infra's _register_central_hook is idempotent-add only; it returns
    on the first match without removing extras. Duplicates can still appear
    via git merges, manual edits, or older buggy sync versions. This check
    surfaces them so `sync_infra.py --execute` (which now runs a dedup pass)
    can clean them up.
    """
    issues: list[str] = []
    settings_path = repo_path / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return issues

    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return issues  # parse errors already flagged by _check_settings

    hooks = settings.get("hooks", {})
    for matcher_type, entries in hooks.items():
        seen: dict[tuple[str, str], int] = {}
        for entry in entries:
            matcher = entry.get("matcher", "")
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                key = (matcher, cmd)
                seen[key] = seen.get(key, 0) + 1
        for (matcher, cmd), count in seen.items():
            if count > 1:
                name_match = re.search(r"hooks/([\w\-]+)\.py", cmd)
                name = name_match.group(1) if name_match else cmd[:40]
                issues.append(
                    f"[{agent}] Duplicate hook registration: "
                    f"{matcher_type}[{matcher or '*'}]:{name} "
                    f"x{count} (run `python tools/sync_infra.py --execute` to clean)"
                )
    return issues


def _check_legacy_settings_json(agent: str, repo_path: Path) -> list[str]:
    """Flag .claude/settings.json (non-local) that may cause hook drift.

    Claude Code merges settings.json + settings.local.json. Legacy/orphan
    settings.json files can silently add duplicate or stale hook regs, or
    enable plugins unintentionally. Known patterns to flag:
      1. settings.json with its own `hooks` block (additive merge risk)
      2. settings.json with `enabledPlugins` (orphan install artifact)

    Canonical home for runtime settings is settings.local.json (this tool's
    audit target).
    """
    issues: list[str] = []
    legacy_path = repo_path / ".claude" / "settings.json"
    if not legacy_path.exists():
        return issues

    try:
        with open(legacy_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        issues.append(f"[{agent}] settings.json present but unparseable: {exc}")
        return issues

    if "hooks" in data:
        issues.append(
            f"[{agent}] settings.json (non-local) declares hooks -- "
            f"merges with settings.local.json and causes duplicate/stale runs; "
            f"migrate entries to settings.local.json and delete settings.json"
        )
    if "enabledPlugins" in data:
        plugins = list(data["enabledPlugins"].keys())
        issues.append(
            f"[{agent}] settings.json enables plugins {plugins} -- "
            f"verify intent; orphan installs should be removed"
        )

    return issues


def _check_stale_local_refs(agent: str, repo_path: Path) -> list[str]:
    """Flag central-hook registrations that still point to a local clone copy.

    sync_infra registers these hooks with an absolute path into agent-core.
    If a clone's settings.local.json references its OWN .claude/hooks/ for
    any CENTRAL_HOOK_NAMES entry, it's running a stale local version
    instead of core's authoritative copy. Next `sync_infra --execute` will
    upgrade it via the 'Points to local copy — upgrade to central reference'
    branch in _register_central_hook.
    """
    issues: list[str] = []
    if agent == "core":
        return issues  # core IS the central location

    settings_path = repo_path / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return issues

    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (json.JSONDecodeError, OSError):
        return issues

    hooks = settings.get("hooks", {})
    for matcher_type, entries in hooks.items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                name_match = re.search(r"hooks/([\w\-]+)\.py", cmd)
                if not name_match:
                    continue
                name = name_match.group(1)
                if name not in CENTRAL_HOOK_NAMES:
                    continue
                if "agent-core" in cmd:
                    continue
                # References a non-core path for a central hook
                issues.append(
                    f"[{agent}] Stale local ref: {matcher_type} {name} "
                    f"points to local clone instead of agent-core "
                    f"(run `python tools/sync_infra.py --execute` to upgrade)"
                )
    return issues


def _fix_missing_hooks(agent: str, repo_path: Path, dry_run: bool = False) -> list[str]:
    """Copy missing synced hooks from core."""
    fixed = []
    core_hooks = AGENTS["core"] / ".claude" / "hooks"
    agent_hooks = repo_path / ".claude" / "hooks"

    if not agent_hooks.exists():
        if not dry_run:
            agent_hooks.mkdir(parents=True, exist_ok=True)
        fixed.append(f"[{agent}] Created .claude/hooks/")

    for hook in REQUIRED_HOOKS:
        src = core_hooks / hook
        dst = agent_hooks / hook

        if not src.exists():
            continue

        if not dst.exists():
            if not dry_run:
                shutil.copy2(src, dst)
            fixed.append(f"[{agent}] Copied {hook} from core")
        elif hook in SYNCED_HOOKS and _md5(src) != _md5(dst):
            if not dry_run:
                shutil.copy2(src, dst)
            fixed.append(f"[{agent}] Updated {hook} to match core")

    return fixed


def main() -> None:
    """Run hook infrastructure audit."""
    parser = argparse.ArgumentParser(description="Audit hook infrastructure")
    parser.add_argument(
        "--fix", action="store_true",
        help="Copy missing/outdated hooks from core"
    )
    args = parser.parse_args()

    all_issues: list[str] = []
    all_fixes: list[str] = []

    print("=" * 60)
    print("Hook Infrastructure Audit")
    print("=" * 60)
    print()

    for agent, repo_path in AGENTS.items():
        if not repo_path.exists():
            print(f"[SKIP] {agent}: repo not found at {repo_path}")
            continue

        issues = []
        issues.extend(_check_hook_files(agent, repo_path))
        issues.extend(_check_hook_versions(agent, repo_path))
        issues.extend(_check_settings(agent, repo_path))
        issues.extend(_check_duplicate_registrations(agent, repo_path))
        issues.extend(_check_legacy_settings_json(agent, repo_path))
        issues.extend(_check_stale_local_refs(agent, repo_path))

        if issues:
            all_issues.extend(issues)
            print(f"[WARN] {agent}: {len(issues)} issue(s)")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"[OK]   {agent}: all checks passed")

        if args.fix and agent != "core":
            fixes = _fix_missing_hooks(agent, repo_path)
            if fixes:
                all_fixes.extend(fixes)
                for fix in fixes:
                    print(f"  [FIX] {fix}")

    print()
    print("-" * 60)
    if all_issues:
        print(f"Total: {len(all_issues)} issue(s) found")
        if all_fixes:
            print(f"Fixed: {len(all_fixes)} issue(s)")
        sys.exit(1)
    else:
        print("All checks passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
