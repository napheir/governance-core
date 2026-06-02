# -*- coding: utf-8 -*-
"""Cross-agent harness infrastructure sync (centralized model).

Deploys core harness capabilities to all agent clones using a
centralized reference pattern that minimizes duplication:

  Hooks   → agents' settings.local.json points to core's scripts
            (zero file copy, one source of truth)
  Commands → copied to each clone (Claude Code requires local files)
  Dirs    → created locally per clone

Architecture principle: "hooks are references, commands are copies."
Hooks can reference any absolute path. Commands must be local.

Usage:
    python tools/sync_infra.py                    # dry-run all agents
    python tools/sync_infra.py --execute          # deploy to all agents
    python tools/sync_infra.py --agent rules      # single agent
    python tools/sync_infra.py --execute --agent trade
"""
import argparse
import json
import logging
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CORE_ROOT = Path(__file__).resolve().parent.parent
PARENT_DIR = CORE_ROOT.parent

# Fallback (P-0059 Phase 2.3b): empty when .governance/config.json is absent.
# Onboarded projects always supply the agent list; an un-onboarded clone
# simply syncs nothing rather than guessing a topology.
_DEFAULT_AGENT_CLONES: dict = {}


def _load_agent_clones_from_config():
    """Map agent name -> clone dir from .governance/config.json (non-core only).

    Returns: dict[str, Path]. Empty dict on any error / missing config.
    """
    cfg_path = CORE_ROOT / ".governance" / "config.json"
    if not cfg_path.exists():
        return dict(_DEFAULT_AGENT_CLONES)
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        install_root = Path(cfg.get("install_root", PARENT_DIR))
        core_name = cfg.get("core_agent_name", "core")
        agents = cfg.get("agents", [])
        if not agents:
            return dict(_DEFAULT_AGENT_CLONES)
        return {
            a["name"]: install_root / a["clone_dir"]
            for a in agents
            if a.get("name") != core_name
        }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[sync_infra] WARN: failed to parse {cfg_path}: {e}; using fallback agent list", file=sys.stderr)
        return dict(_DEFAULT_AGENT_CLONES)


AGENT_CLONES = _load_agent_clones_from_config()

# Non-skill files that are always propagated core → all clones.
#
# Three categories of content live here:
#
# 1. Generator source (constitution/total.md): each clone regenerates its
#    own CLAUDE.md locally, but from the core-authoritative total.md.
#
# 2. Scope-guard hooks (.claude/hooks/edit-write-guard.py, scope-guard.py):
#    MUST be per-clone physical copies (not CENTRAL_HOOKS references)
#    because each hook resolves _REPO_ROOT relative to its own location —
#    the hook must live inside the clone whose branch/role it enforces.
#
# 3. Shared contracts + shared knowledge tooling: each clone needs its
#    own copy so local tooling (audit_knowledge.py etc.) works without
#    cross-clone reads. When a contract or tool evolves in core, next
#    sync_infra --execute propagates it. This replaces the pattern where
#    agents only got tooling updates through full master merges.
# P-0059 Phase 2.3b: the list below is the FALLBACK only. Authoritative
# source is .governance/sync_files.json (project-specific). The fallback
# stays verbatim so an un-onboarded clone still syncs core infrastructure.
_FALLBACK_ALWAYS_COPY_FILES = [
    # Generator source
    "constitution/total.md",

    # Scope guards (per-clone copy; must see clone's git branch)
    ".claude/hooks/edit-write-guard.py",
    ".claude/hooks/scope-guard.py",
    ".claude/hooks/data-source-guard.py",
    ".claude/hooks/_guard_common.py",

    # Shared contracts (read by any agent reading/writing the federated data)
    "contracts/__init__.py",
    "contracts/versions.json",
    "contracts/features_schema.json",
    "contracts/feature_center_contract.md",
    "contracts/strangle_signal_contract.md",
    "contracts/strangle50_signal_contract.md",
    "contracts/knowledge_frontmatter_schema.md",
    "contracts/knowledge_index_schema.md",

    # Shared knowledge-federation tools (run per-clone against local knowledge/)
    "tools/audit_knowledge.py",
    "tools/diff_classify.py",
    # gc #24 (P-0091): build_knowledge_dashboard.py released to business
    # ownership -- gc no longer distributes a knowledge renderer.
    "tools/build_skill_index.py",
    "tools/skill_catalog.py",
    "tools/migrate_knowledge_frontmatter.py",
    "tools/validate_routing.py",
    "tools/audit_proposals.py",
    "tools/audit_sub_constitutions.py",
    "tools/backfill_proposal_status.py",
    "tools/proposal_lib.py",
    "tools/infer_carrier_class.py",
    # gc #24 (P-0091): build_autogen_blocks.py released to business ownership.
    "tools/audit_html_profile.py",
    "contracts/proposal_frontmatter_schema.md",
    "config/proposals_config.json",

    # Pre-commit scope enforcement (run per-clone against local scope rules
    # by .git/hooks/pre-commit). Must propagate so encoding fixes etc. land
    # in all clones immediately, not only after each one merges master.
    "tools/check_scope.py",

    # Prompt-context router config (per-clone copy because each agent reads
    # its own knowledge/governance/ tree relative to its repo root)
    "knowledge/INDEX.routing.json",

    # Knowledge HTML profile rendering assets (P-0054). Every clone with
    # `knowledge/**/*.html` files (P-0054 Phase 3 harness_defense.html,
    # Phase 5 s50_current.html, future migrations) must have local
    # CSS / JS / vendored Mermaid runtime to render those pages offline.
    # Without these the HTML files render blank text.
    "knowledge/assets/knowledge.css",
    "knowledge/assets/knowledge.js",
    "knowledge/assets/_fixture.html",
    "knowledge/assets/vendor/mermaid/mermaid.min.js",
    "knowledge/assets/vendor/mermaid/VERSION.md",
    # Cytoscape vendored 2026-05-13 (same offline-first rationale; see
    # commit 96e4ccce). build_knowledge_dashboard.py's vendored_assets
    # loop will FileNotFoundError in any clone missing this pair.
    "knowledge/assets/vendor/cytoscape/cytoscape.min.js",
    "knowledge/assets/vendor/cytoscape/VERSION.md",
    # .gitattributes marks knowledge/assets/vendor/** binary so Windows
    # clones (core.autocrlf=true) do not CRLF-convert vendored bundles
    # and invalidate the sha256 recorded in each VERSION.md.
    ".gitattributes",

    # Destructive-command guard data (proposals/harden_destructive_command_guard.md).
    # Every clone needs the new regex-deny + allow-prefix files locally so its
    # command-guard.py can read them. The hook itself uses _REPO_ROOT so it
    # resolves these relative to the clone, not core.
    "agent_rules/shared.deny_commands.txt",
    "agent_rules/shared.deny_commands_regex.txt",
    "agent_rules/shared.allow_commands.txt",

    # Forward-looking principle for least-privilege at resource layer (DB / API).
    "knowledge/governance/agent-least-privilege.md",

    # Boundary anchor for session-boundary-guard.py (proposal #3).
    # Each clone's settings.json declares projectRoot=../, so the hook
    # walking up from cwd in any of the 5 clones lands on
    # <install-root>/ as the boundary -- enabling cross-clone work for
    # core agent + intra-project work for the others, while still
    # blocking writes outside <install-root>/.
    ".claude/settings.json",

    # Session-boundary-guard source files. The hook itself runs from
    # ~/.claude/hooks/ (user-global, deployed by install_session_
    # boundary_guard.ps1). Each clone keeps a tracked source copy so:
    # (1) any clone owner can re-deploy or test the guard locally;
    # (2) any change to the guard propagates to all 5 clones via
    #     sync_infra, keeping the source in lockstep with master;
    # (3) the smoke tests work from any clone.
    "tools/derive_session_boundary.py",
    "tools/session-boundary-guard.py",
    "tools/install_session_boundary_guard.ps1",
    "tools/test_derive_session_boundary.py",
    "tools/test_session_boundary_guard.py",

    # P-0058 Phase 1: classify gate soft reminder (user-global hook).
    # Versioned source in tools/; deployed to ~/.claude/hooks/ via the
    # manual one-liner documented in core-manual §11.5b (install note).
    "tools/proposal-classify-reminder.py",
    "tools/proposal-classify-keywords.json",

    # Phase B/C/D of proposal harden_indirect_attack_paths.md.
    "tools/test_edit_write_destructive_scan.py",
    "tools/test_repo_health_alarm.py",
    "knowledge/governance/resource-layer-hardening.md",
]


def _load_always_copy_files():
    """Try .governance/sync_files.json:always_copy_files; fallback to hardcoded.

    Returns: list of relative paths (preserving order).
    """
    sf_path = CORE_ROOT / ".governance" / "sync_files.json"
    if not sf_path.exists():
        return list(_FALLBACK_ALWAYS_COPY_FILES)
    try:
        data = json.loads(sf_path.read_text(encoding="utf-8"))
        files = data.get("always_copy_files")
        if isinstance(files, list) and files:
            return files
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        print(f"[sync_infra] WARN: failed to parse {sf_path}: {e}; using fallback", file=sys.stderr)
    return list(_FALLBACK_ALWAYS_COPY_FILES)


ALWAYS_COPY_FILES = _load_always_copy_files()

# Scope-guard hook filenames referenced in settings.local.json. Used by
# _fix_guard_references to rewrite any command that accidentally points
# at agent-core's copy back to the current clone's local copy (running
# the core copy makes _detect_role see master → role=core → bypass).
SCOPE_GUARD_HOOKS = [
    "edit-write-guard.py",
    "scope-guard.py",
    "data-source-guard.py",
]

# Authored skill directories scanned for theme-based routing (see
# _discover_themed_copies). Each .md file in these dirs must carry a
# `theme:` frontmatter field (universal | core-only | <agent-name>).
#
# .claude/skills/ holds cross-agent guides (type: guide) that should
# propagate to every clone so Registry L0 scan in non-core agents can
# surface them. .claude/skills/learned/ is EXPLICITLY NOT included —
# those are per-agent session extractions per the
# shared-code-per-agent-state pattern (learned skills belong in the
# invoker's clone, not pushed from core). glob("*.md") is non-recursive
# so learned/ is skipped naturally.
SKILL_DIRS = [
    ".claude/commands",
    ".claude/agents",
    ".claude/skills",
]

# Valid theme values.
THEMES_UNIVERSAL = "universal"
THEMES_CORE_ONLY = "core-only"
# Per-agent themes equal agent names in AGENT_CLONES.

# Hooks to REFERENCE centrally (no file copy — settings.json points to core)
# Format: (hook_name, core_relative_path, matcher_type, timeout)
#
# Retired entries (pruned via _cleanup_stale_central_refs in each clone):
#   skill-nudge.py      -- deprecated in commit 3bf3891
#   session-summary.py  -- file retired; dedup+centralize commits left stale refs
#   context-reminder.py -- replaced by constitution-reminder.py (same purpose)
CENTRAL_HOOKS = [
    ("session-context", ".claude/hooks/session-context.py", "SessionStart", 10),
    ("constitution-reminder", ".claude/hooks/constitution-reminder.py", "UserPromptSubmit", 5),
    # Tracks skill invocations so weighted_scores() / should_extract() have
    # real data. Registered on both matchers to capture user /slash-commands
    # and Claude's Skill tool loads; hook self-filters by event + tool name.
    # Q5 audit fix 2026-04-28: PostToolUse-only (no UserPromptSubmit)
    # to avoid double-counting user-typed /slash + harness-invoked Skill.
    ("skill-usage-tracker", ".claude/hooks/skill-usage-tracker.py", "PostToolUse", 3),
    # Conditionally injects knowledge/governance/* docs when user prompt
    # contains a trigger keyword. Replaces "everything in the constitution"
    # — see proposals/slim_constitution_via_registry_and_router.md Phase 2.
    ("prompt-context-router", ".claude/hooks/prompt-context-router.py", "UserPromptSubmit", 5),
    # PostToolUse audit: detect git repo damage (HEAD backward, .git deleted,
    # branch count drop >= 2). Non-blocking, alerts to <repo>/audit/
    # repo_health_alerts.jsonl + stderr. Per
    # proposals/harden_destructive_command_guard.md sec.2.4. Hook reads
    # os.getcwd() to identify which clone -- safe to centralize.
    ("repo-health", ".claude/hooks/repo-health.py", "PostToolUse", 5),
    # UserPromptSubmit nudge: warn (stderr only, NOT stdout -- stdout would
    # enter prompt prefix and partially defeat the purpose) when avg
    # cache_read over last 10 turns crosses 600k. Hook reads transcript_path
    # from stdin (always absolute), so per-clone scope detection unnecessary
    # -- centralization safe. Per proposals/prefix_cost_optimization.md
    # Change B (approved 2026-05-07).
    ("cache-watchdog", ".claude/hooks/cache-watchdog.py", "UserPromptSubmit", 5),
]

# Per-clone settings.local.json allow-list rewrites (resolved sec.8 Q4).
# Replaces wide entries like Bash(rm:*) with narrow path-prefix variants;
# sync_infra acts as the permanent enforcement mechanism (option a from
# sec.2.5 / sec.8 Q4). Entries are (wide_to_remove, narrow_replacements_list).
# Per proposals/harden_destructive_command_guard.md sec.2.5 + sec.8 Q4.
SETTINGS_LOCAL_ALLOW_REWRITES = [
    ("Bash(rm:*)", [
        "Bash(rm /tmp/*)",
        "Bash(rm -f /tmp/*)",
        "Bash(rm -f ~/.claude/cache/*)",
        "Bash(rm -f *.tmp)",
        "Bash(rm -f *.log)",
    ]),
    ("Bash(del:*)", [
        "Bash(del /q *.tmp)",
    ]),
    ("Bash(powershell:*)", [
        "Bash(powershell -NoProfile -Command Get-*)",
        "Bash(powershell -NoProfile -Command Test-Path*)",
        "Bash(powershell -NoProfile -Command Select-String*)",
    ]),
    ("Bash(pwsh:*)", [
        "Bash(pwsh -NoProfile -Command Get-*)",
        "Bash(pwsh -NoProfile -Command Test-Path*)",
        "Bash(pwsh -NoProfile -Command Select-String*)",
    ]),
]

# Drift detection: any of these wide entries reappearing in a clone is a
# regression of the sec.2.5 tightening (someone re-added the wildcard).
SETTINGS_LOCAL_DRIFT_WIDE_ENTRIES = frozenset(
    wide for wide, _ in SETTINGS_LOCAL_ALLOW_REWRITES
)

# Directories to ensure exist in each agent clone
ENSURE_DIRS = [
    ".claude/skills/learned",
]


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file.

    Returns empty dict if no frontmatter present. Parser is deliberately
    tiny (no PyYAML dep) — handles `key: value` and `- item` list forms
    sufficient for our theme/owner/tools usage.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fm_body = text[4:end]
    result: dict = {}
    current_list_key: str | None = None
    for line in fm_body.splitlines():
        if not line.strip():
            current_list_key = None
            continue
        if line.startswith("  - ") and current_list_key:
            result[current_list_key].append(line[4:].strip())
            continue
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                result[key] = value
                current_list_key = None
            else:
                result[key] = []
                current_list_key = key
    return result


def _discover_themed_copies(agent_name: str) -> list[tuple[Path, str]]:
    """Return (source_path, relative_path) pairs to copy for a given agent.

    Scans SKILL_DIRS in core. A file is included when:
      - theme == "universal"                  → copy to all clones
      - theme == agent_name                   → copy to that specific clone
      - theme == "core-only"                  → skip (stays only in core)
    Missing/invalid theme raises — frontmatter discipline is enforced here
    so new skills can't silently bypass routing.
    """
    result: list[tuple[Path, str]] = []
    valid_per_agent = set(AGENT_CLONES.keys())
    for skill_dir in SKILL_DIRS:
        abs_dir = CORE_ROOT / skill_dir
        if not abs_dir.is_dir():
            continue
        for md in sorted(abs_dir.glob("*.md")):
            fm = _parse_frontmatter(md)
            theme = fm.get("theme")
            if not theme:
                raise ValueError(
                    f"{md.relative_to(CORE_ROOT)}: missing `theme:` frontmatter. "
                    f"Add `theme: universal | core-only | <agent>` (e.g. trade)."
                )
            if theme == THEMES_CORE_ONLY:
                continue
            if theme == THEMES_UNIVERSAL:
                result.append((md, f"{skill_dir}/{md.name}"))
                continue
            if theme in valid_per_agent:
                if theme == agent_name:
                    result.append((md, f"{skill_dir}/{md.name}"))
                continue
            raise ValueError(
                f"{md.relative_to(CORE_ROOT)}: invalid theme={theme!r}. "
                f"Allowed: universal, core-only, {sorted(valid_per_agent)}"
            )
    return result


def _copy_file(src: Path, dst: Path, dry_run: bool) -> str:
    """Copy a file from core to agent clone.

    Args:
        src: Source file in agent-core.
        dst: Destination in agent clone.
        dry_run: If True, don't actually copy.

    Returns:
        Status string.
    """
    if not src.exists():
        return f"  [SKIP] {src.name} -- source missing in core"

    if dst.exists():
        src_content = src.read_text(encoding="utf-8")
        dst_content = dst.read_text(encoding="utf-8")
        if src_content == dst_content:
            return f"  [OK]   {dst.name} -- already up to date"

    if dry_run:
        return f"  [COPY] {dst.name} -- would copy"

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return f"  [COPY] {dst.name} -- copied"


def _ensure_dir(target: Path, dry_run: bool) -> str:
    """Ensure a directory exists.

    Args:
        target: Directory path.
        dry_run: If True, don't create.

    Returns:
        Status string.
    """
    if target.exists():
        return f"  [OK]   {target.name}/ -- exists"

    if dry_run:
        return f"  [MKDIR] {target.name}/ -- would create"

    target.mkdir(parents=True, exist_ok=True)
    return f"  [MKDIR] {target.name}/ -- created"


def _remove_local_copy(agent_dir: Path, rel_path: str, dry_run: bool) -> str:
    """Remove a previously-copied file that is now centrally referenced.

    Args:
        agent_dir: Agent clone root.
        rel_path: Relative path to the file.
        dry_run: If True, don't delete.

    Returns:
        Status string.
    """
    target = agent_dir / rel_path
    if not target.exists():
        return ""  # nothing to remove
    if dry_run:
        return f"  [DEL]  {target.name} -- would remove local copy (now centralized)"
    target.unlink()
    return f"  [DEL]  {target.name} -- removed local copy (now centralized)"


def _register_central_hook(
    agent_dir: Path,
    hook_name: str,
    core_hook_path: Path,
    matcher_type: str,
    timeout: int,
    dry_run: bool,
) -> str:
    """Register a hook that references core's script via absolute path.

    This is the key centralization mechanism: no file is copied to the
    agent clone. Instead, settings.local.json points to core's script.

    Args:
        agent_dir: Agent clone root directory.
        hook_name: Human-readable hook name (for detection).
        core_hook_path: Absolute path to the hook script in agent-core.
        matcher_type: Hook event type (Notification, PreToolUse, etc.).
        timeout: Hook timeout in seconds.
        dry_run: If True, don't modify.

    Returns:
        Status string.
    """
    settings_path = agent_dir / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return f"  [SKIP] settings.local.json -- not found"

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return f"  [FAIL] settings.local.json -- parse error: {e}"

    hooks = settings.setdefault("hooks", {})
    matcher_entries = hooks.setdefault(matcher_type, [])

    core_command = f"python {core_hook_path.as_posix()}"

    # Check if already registered (by hook name in command string)
    for entry in matcher_entries:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if hook_name in cmd:
                # Already registered — check if it points to core
                if "agent-core" in cmd:
                    return f"  [OK]   {hook_name} -- centralized (points to core)"
                # Points to local copy — upgrade to central reference
                if not dry_run:
                    hook["command"] = core_command
                    settings_path.write_text(
                        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                    return f"  [UPD]  {hook_name} -- upgraded to central reference"
                return f"  [UPD]  {hook_name} -- would upgrade to central reference"

    # Not registered yet — add with central reference
    target_entry = None
    for entry in matcher_entries:
        if entry.get("matcher", "") == "":
            target_entry = entry
            break
    if target_entry is None:
        target_entry = {"matcher": "", "hooks": []}
        matcher_entries.append(target_entry)

    new_hook = {
        "type": "command",
        "command": core_command,
        "timeout": timeout,
    }

    if dry_run:
        return f"  [ADD]  {hook_name} -- would register (central reference)"

    target_entry["hooks"].append(new_hook)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return f"  [ADD]  {hook_name} -- registered (central reference)"


def _cleanup_stale_central_refs(agent_dir: Path, dry_run: bool) -> list[str]:
    """Remove settings references to CORE hooks whose files no longer exist.

    When a central hook is renamed or deleted (e.g. context-reminder.py
    retired in favor of constitution-reminder.py), _register_central_hook
    only adds/upgrades -- it never prunes. Stale references to deleted
    files then break UserPromptSubmit and other hook events in each
    clone. This pass scans every clone's settings.local.json for
    `{CORE_ROOT}/.claude/hooks/<name>.py` references and drops any
    whose target file is missing in core.

    Only touches references into CORE's hook directory -- local hooks
    under `{this-clone}/.claude/hooks/` are left alone.

    Args:
        agent_dir: Agent clone root directory.
        dry_run: If True, don't write.

    Returns:
        List of status strings.
    """
    settings_path = agent_dir / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return []
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"  [FAIL] settings.local.json -- parse error: {exc}"]

    if "hooks" not in settings:
        return []
    hooks = settings["hooks"]
    results: list[str] = []
    changed = False
    core_prefix = CORE_ROOT.as_posix()
    ref_pattern = re.compile(
        re.escape(core_prefix) + r"/(\.claude/hooks/[\w\-]+\.py)"
    )

    for matcher_type, entries in hooks.items():
        for entry in entries:
            if "hooks" not in entry:
                continue
            kept: list[dict] = []
            for h in entry["hooks"]:
                cmd = h["command"] if "command" in h else ""
                matches = ref_pattern.findall(cmd)
                missing = [m for m in matches if not (CORE_ROOT / m).is_file()]
                if missing:
                    for m in missing:
                        results.append(
                            f"  [STALE] {m} -- removed (file missing in core)"
                        )
                    changed = True
                    continue
                kept.append(h)
            entry["hooks"] = kept

    if changed and not dry_run:
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return results


def _fix_guard_references(agent_dir: Path, dry_run: bool) -> list[str]:
    """Rewrite scope-guard hook references in settings.local.json.

    Each clone must run its own local copy of edit-write-guard.py /
    scope-guard.py so the hook's _REPO_ROOT resolves to that clone and
    _detect_role returns the clone's role (from its feature branch).
    Historically three non-core clones had references pointing at
    agent-core's copy — making the guard run with role=core and bypass
    all scope checks. This pass rewrites any such reference to the
    clone's local path.

    Args:
        agent_dir: Agent clone root directory.
        dry_run: If True, don't modify.

    Returns:
        List of status strings.
    """
    settings_path = agent_dir / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return [f"  [SKIP] settings.local.json -- not found"]

    text = settings_path.read_text(encoding="utf-8")
    results: list[str] = []
    changed = False
    core_prefix = CORE_ROOT.as_posix()
    local_prefix = agent_dir.as_posix()

    if core_prefix == local_prefix:
        return []  # core itself — no rewriting needed

    for guard in SCOPE_GUARD_HOOKS:
        core_ref = f"{core_prefix}/.claude/hooks/{guard}"
        local_ref = f"{local_prefix}/.claude/hooks/{guard}"
        if core_ref in text:
            if dry_run:
                results.append(f"  [FIX]  {guard} -- would rewrite core -> local")
            else:
                text = text.replace(core_ref, local_ref)
                changed = True
                results.append(f"  [FIX]  {guard} -- rewrote core -> local")

    if changed and not dry_run:
        settings_path.write_text(text, encoding="utf-8")

    return results


def _cleanup_duplicates(agent_dir: Path, dry_run: bool) -> list[str]:
    """Remove duplicate hook registrations within each matcher bucket.

    Historical sync runs, git merge conflicts, or manual edits can leave
    identical (matcher, command) pairs in settings.local.json. The main
    dedup check in _register_central_hook returns on the first match, so
    pre-existing duplicates are never pruned. This pass scans every
    matcher bucket and removes exact command duplicates, keeping the first.
    """
    settings_path = agent_dir / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return []

    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"  [FAIL] settings.local.json -- parse error: {exc}"]

    hooks = settings.get("hooks", {})
    results: list[str] = []
    changed = False

    for matcher_type, entries in hooks.items():
        seen: set[tuple[str, str]] = set()
        for entry in entries:
            matcher = entry.get("matcher", "")
            kept: list[dict] = []
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                key = (matcher, cmd)
                if key in seen:
                    name_match = re.search(r"hooks/([\w\-]+)\.py", cmd)
                    name = name_match.group(1) if name_match else cmd[:40]
                    results.append(
                        f"  [DEDUP] {matcher_type}[{matcher or '*'}]:{name} "
                        f"-- removed duplicate"
                    )
                    changed = True
                    continue
                seen.add(key)
                kept.append(hook)
            entry["hooks"] = kept

        # Drop entries that end up with zero hooks (orphan / leftover shells).
        # Preserve one matcher="" slot for future central registrations.
        pruned: list[dict] = []
        empty_default_kept = False
        for entry in entries:
            if entry.get("hooks"):
                pruned.append(entry)
                continue
            if entry.get("matcher", "") == "" and not empty_default_kept:
                pruned.append(entry)
                empty_default_kept = True
                continue
            results.append(
                f"  [PRUNE] {matcher_type}[{entry.get('matcher') or '*'}] "
                f"-- removed empty entry"
            )
            changed = True
        hooks[matcher_type] = pruned

    if changed and not dry_run:
        settings_path.write_text(
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return results


def _tighten_settings_local_allow(agent_dir: Path, dry_run: bool) -> list[str]:
    """Replace wide allow entries with narrow prefix variants in settings.local.json.

    Implements sec.2.5 + sec.8 Q4 of harden_destructive_command_guard.md as
    the permanent enforcement mechanism (option a -- one-shot scripts get
    forgotten and drift recurs). Idempotent: re-running is safe; missing
    wide entries are skipped, missing narrow entries are added once.

    Also detects drift: if a wide entry reappears in a clone (someone
    re-added Bash(rm:*) by hand), warn but do not auto-remove without
    re-applying the rewrite.

    Args:
        agent_dir: Agent clone root directory.
        dry_run: If True, don't write.

    Returns:
        List of status strings.
    """
    settings_path = agent_dir / ".claude" / "settings.local.json"
    if not settings_path.exists():
        return ["  [SKIP] settings.local.json -- not found"]
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"  [FAIL] settings.local.json -- parse error: {exc}"]

    permissions = settings.setdefault("permissions", {})
    allow = permissions.setdefault("allow", [])
    if not isinstance(allow, list):
        return ["  [FAIL] permissions.allow not a list"]

    results: list[str] = []
    changed = False

    # Pass 1: remove wide entries, queue their replacements for insertion at
    # the same position (preserves overall ordering).
    new_allow: list[str] = []
    pending_inserts: list[str] = []
    for entry in allow:
        if entry in SETTINGS_LOCAL_DRIFT_WIDE_ENTRIES:
            # Find its replacement set and queue narrows in place.
            for wide, narrows in SETTINGS_LOCAL_ALLOW_REWRITES:
                if wide == entry:
                    pending_inserts.extend(narrows)
                    break
            results.append(f"  [TIGHTEN] removed wide entry {entry}")
            changed = True
            continue
        new_allow.append(entry)
        # Flush queued narrows after the position the wide entry occupied.
        if pending_inserts:
            for narrow in pending_inserts:
                if narrow not in new_allow:
                    new_allow.append(narrow)
                    results.append(f"  [TIGHTEN] added narrow entry {narrow}")
                    changed = True
            pending_inserts = []

    # Any remaining narrows (wide was last in list) -> append at end.
    for narrow in pending_inserts:
        if narrow not in new_allow:
            new_allow.append(narrow)
            results.append(f"  [TIGHTEN] added narrow entry {narrow}")
            changed = True

    # Pass 2: ensure all canonical narrows are present (in case clone was
    # never tightened or someone removed a narrow entry). Append missing
    # ones at end -- ordering relative to wides already handled above.
    for _, narrows in SETTINGS_LOCAL_ALLOW_REWRITES:
        for narrow in narrows:
            if narrow not in new_allow:
                new_allow.append(narrow)
                results.append(f"  [TIGHTEN] added missing narrow entry {narrow}")
                changed = True

    if changed:
        permissions["allow"] = new_allow
        if not dry_run:
            settings_path.write_text(
                json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    if not changed:
        results.append("  [OK] settings.local.json -- already tightened")
    return results


def sync_agent(agent_name: str, agent_dir: Path, dry_run: bool) -> tuple[list[str], bool]:
    """Sync infrastructure to a single agent clone.

    Args:
        agent_name: Agent name (rules, trade, data, research).
        agent_dir: Agent clone root directory.
        dry_run: If True, don't make changes.

    Returns:
        (results, commands_changed) — status lines and a flag indicating
        whether any slash-command file was copied (triggers a session
        restart reminder in the caller).
    """
    results = [f"\n{'='*50}", f"Agent: {agent_name} ({agent_dir.name})"]
    commands_changed = False

    if not agent_dir.exists():
        results.append("  [SKIP] Directory not found")
        return results, commands_changed

    mode = "DRY-RUN" if dry_run else "EXECUTE"
    results.append(f"Mode: {mode}")
    results.append("")

    # 1. Copy generator sources (constitution/total.md etc)
    results.append("Generator sources (always):")
    for rel_path in ALWAYS_COPY_FILES:
        src = CORE_ROOT / rel_path
        dst = agent_dir / rel_path
        results.append(_copy_file(src, dst, dry_run))

    # 2. Copy themed skills (theme-driven discovery)
    results.append("\nSkills (theme-driven):")
    for src, rel_path in _discover_themed_copies(agent_name):
        dst = agent_dir / rel_path
        msg = _copy_file(src, dst, dry_run)
        results.append(msg)
        if "[COPY]" in msg:
            commands_changed = True

    # 2. Register hooks via central reference (no file copy)
    results.append("\nHooks (central reference -> core):")
    for hook_name, rel_path, matcher, timeout in CENTRAL_HOOKS:
        core_hook = CORE_ROOT / rel_path

        # Remove any local copy from previous sync model
        cleanup = _remove_local_copy(agent_dir, rel_path, dry_run)
        if cleanup:
            results.append(cleanup)

        # Register central reference in settings.json
        results.append(
            _register_central_hook(
                agent_dir, hook_name, core_hook, matcher, timeout, dry_run
            )
        )

    # 3. Ensure directories
    results.append("\nDirectories:")
    for rel_path in ENSURE_DIRS:
        target = agent_dir / rel_path
        results.append(_ensure_dir(target, dry_run))

    # 4. Rewrite scope-guard hook refs from core -> this clone
    #    (fixes a latent bug where trade/data/research pointed at core's
    #    guard and silently ran role=core, bypassing Layer 1/2/3.)
    guard_results = _fix_guard_references(agent_dir, dry_run)
    if guard_results:
        results.append("\nGuard references (settings.local.json):")
        results.extend(guard_results)

    # 4b. Remove stale references to core hooks that no longer exist
    #     (renamed / deleted central hooks leave broken command strings
    #     pointing into CORE_ROOT; must be pruned so UserPromptSubmit et
    #     al. do not error.)
    stale_results = _cleanup_stale_central_refs(agent_dir, dry_run)
    if stale_results:
        results.append("\nStale central refs (settings.local.json):")
        results.extend(stale_results)

    # 5. Cleanup duplicate hook registrations in matcher buckets
    #    (git merges / manual edits / older buggy sync runs can leak dupes;
    #    the registration path only checks idempotent-add, never prunes.)
    dedup_results = _cleanup_duplicates(agent_dir, dry_run)
    if dedup_results:
        results.append("\nDedup (settings.local.json):")
        results.extend(dedup_results)

    # 6. Tighten allow-list per harden_destructive_command_guard.md sec.2.5.
    #    Replaces wide entries (Bash(rm:*) etc.) with narrow path-prefix
    #    variants; idempotent + drift-detecting.
    tighten_results = _tighten_settings_local_allow(agent_dir, dry_run)
    if any("[TIGHTEN]" in r or "[FAIL]" in r for r in tighten_results):
        results.append("\nAllow-list tightening (settings.local.json):")
        results.extend(tighten_results)

    return results, commands_changed


def sync_all(agents: list[str], dry_run: bool) -> None:
    """Sync infrastructure to specified agent clones.

    Args:
        agents: List of agent names to sync.
        dry_run: If True, don't make changes.
    """
    print("Harness Infrastructure Sync (Centralized Model)")
    print(f"Source: {CORE_ROOT}")
    print(f"Mode: {'DRY-RUN' if dry_run else 'EXECUTE'}")
    print(f"\nArchitecture: hooks=reference, commands=copy")

    total_actions = 0
    agents_needing_restart: list[str] = []
    for name in agents:
        agent_dir = AGENT_CLONES.get(name)
        if agent_dir is None:
            print(f"\n[FAIL] Unknown agent: {name}")
            continue

        results, commands_changed = sync_agent(name, agent_dir, dry_run)
        if commands_changed:
            agents_needing_restart.append(name)
        for line in results:
            print(line)
            if any(tag in line for tag in ["[COPY]", "[MKDIR]", "[ADD]", "[UPD]", "[DEL]"]):
                total_actions += 1

    print(f"\n{'='*50}")
    if dry_run:
        print(f"Total pending actions: {total_actions}")
        print("Run with --execute to apply.")
    else:
        print(f"Total actions applied: {total_actions}")
        print("[OK] Sync complete.")

    # Slash-command cache warning: Claude Code loads .claude/commands/*.md
    # into the session at startup and does not hot-reload. Any agent whose
    # command files were (or would be) modified must exit and re-open its
    # Claude Code session for the new definitions to take effect.
    # See .claude/skills/slash-command-hot-reload.md for the full rule.
    if agents_needing_restart:
        verb = "would be updated" if dry_run else "were updated"
        print("")
        print("=" * 50)
        print(f"[RESTART REQUIRED] Slash-command files {verb} for:")
        for name in agents_needing_restart:
            print(f"  - {name}")
        print("")
        print("Claude Code caches slash-command definitions at session start.")
        print("Running sessions in these clones must EXIT and re-open for the")
        print("new /wrap-up, /extract-skill, etc. to take effect.")
        print("Guide: .claude/skills/slash-command-hot-reload.md")

        # R9 (harness audit 2026-04-28): drop a marker file so the NEXT
        # SessionStart in any clone re-surfaces this warning even if user
        # missed the stdout. session-context.py reads + clears the marker
        # on first display (single-shot per-clone).
        if not dry_run:
            import json as _json
            import time as _time
            from pathlib import Path as _Path
            marker = _Path.home() / ".claude" / "cache" / "restart_required.json"
            try:
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(
                    _json.dumps({
                        "ts": _time.time(),
                        "clones": list(agents_needing_restart),
                        "reason": "slash-command files updated",
                    }),
                    encoding="utf-8",
                )
            except OSError:
                pass


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Cross-agent harness infrastructure sync (centralized)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes (default: dry-run)",
    )
    parser.add_argument(
        "--agent",
        type=str,
        default=None,
        choices=list(AGENT_CLONES.keys()),
        help="Sync single agent (default: all)",
    )
    args = parser.parse_args()

    agents = [args.agent] if args.agent else list(AGENT_CLONES.keys())
    sync_all(agents, dry_run=not args.execute)


if __name__ == "__main__":
    main()
