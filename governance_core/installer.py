"""governance-core installer — sets up downstream project's .governance/ + .claude/.

Phase 1.4 minimal implementation: copy-based (no symlinks for cross-platform
simplicity; future versions may use symlinks on POSIX).

Strategy:

1. Read or create `.governance/config.json` (merge with config_overrides if any)
2. For each governance asset category, copy from package resources to project:
     hooks -> .claude/hooks/
     skills -> .claude/skills/
     commands -> .claude/commands/
     agents -> .claude/agents/
     contracts -> contracts/
     agent_rules (shared.*) -> agent_rules/
     clauses -> .governance/clauses/ (with placeholder substitution)
     knowledge_governance -> knowledge/governance/ (with subdirs)
3. Configure .gitattributes for per-branch agent.md merge=ours driver
4. Run `git config merge.ours.driver true` (best-effort; fails silently on
   non-git projects)

config.json schema:

    {
      "project_name": str,
      "install_root": str (path),
      "shared_state_root": str (path),
      "claude_dir": str (".claude"),
      "core_agent_name": str ("core"),
      "core_branches": [str] (["master"]),
      "ritual_phrase": str ("Acknowledged"),
      "agents": [{"name": str, "branch": str, "clone_dir": str}],
      "upstream_branch": str ("origin/master"),
      "constitution_layout": {...}
    }
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger("governance_core.installer")

# Package root (path to governance_core/ directory)
PKG_ROOT = Path(__file__).resolve().parent

CONFIG_REL = ".governance/config.json"
CLAUSES_REL = ".governance/clauses"
CLAUDE_DIR = ".claude"

# Category -> (source-subdir-in-pkg, destination-subdir-in-project)
COPY_CATEGORIES = [
    ("hooks",     ".claude/hooks"),
    ("skills",    ".claude/skills"),
    ("commands",  ".claude/commands"),
    ("agents",    ".claude/agents"),
    ("contracts", "contracts"),
    ("agent_rules", "agent_rules"),
    ("tools",     "tools"),
]

KNOWLEDGE_COPY_MAP = [
    ("knowledge_governance", "knowledge/governance"),
    ("knowledge_governance/methodology", "knowledge/methodology"),
    ("knowledge_governance/design", "knowledge/design"),
    ("knowledge_governance/operations", "knowledge/operations"),
]

# Mixed clauses (P-0063 方案 A): generic frame + project-specific business
# tables. The installer renders a generic stub on first install but never
# overwrites an existing copy — the downstream project owns the business
# content of these clauses in full.
MIXED_CLAUSES = {
    "art_01_project_architecture.md",
    "art_02_directory_responsibilities.md",
    "art_02b_core_audit_responsibilities.md",
    "art_03_contracts.md",
    "art_04_config_management.md",
    "art_04b_shared_runtime_state.md",
    "art_10_artifacts_layout.md",
}

GITATTRIBUTES_RULE = (
    "# governance-core: per-branch agent.md isolation via merge=ours driver\n"
    "constitution/agent.md merge=ours\n"
)


DEFAULT_CONFIG: dict[str, Any] = {
    "$schema_version": "0.1.0",
    "project_name": "example-project",
    "install_root": str(Path.home() / "workshop-claude"),
    "shared_state_root": str(Path.home() / "workshop-claude" / "example-project" / "shared_state"),
    "claude_dir": ".claude",
    "core_agent_name": "core",
    "core_branches": ["master", "main"],
    "ritual_phrase": "Acknowledged",
    "agents": [
        {"name": "core", "branch": "master", "clone_dir": "agent-core"},
        {"name": "data", "branch": "feature/data", "clone_dir": "agent-data"},
    ],
    "upstream_branch": "origin/master",
    "constitution_layout": {
        "total_md_path": "constitution/total.md",
        "agent_md_path": "constitution/agent.md",
        "claude_md_mirror": "CLAUDE.md",
    },
}


def _load_or_init_config(
    project_root: Path,
    config_overrides: dict[str, Any],
    preserve_config: bool,
) -> dict[str, Any]:
    cfg_path = project_root / CONFIG_REL
    if cfg_path.exists() and preserve_config:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg_path.exists():
        existing = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        existing = DEFAULT_CONFIG.copy()
    # Shallow merge overrides
    for k, v in config_overrides.items():
        existing[k] = v
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("[config] wrote %s", cfg_path)
    return existing


def _copy_tree(src: Path, dst: Path) -> int:
    """Copy a directory tree; returns file count. Overwrites existing files."""
    if not src.exists():
        logger.warning("[copy] source missing: %s", src)
        return 0
    n = 0
    for s in src.rglob("*"):
        if s.is_dir():
            continue
        if s.name == "README.md" and s.parent == src:
            # Skip per-category READMEs in the package (they're just docs)
            continue
        rel = s.relative_to(src)
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
        n += 1
    return n


def _render_clauses(project_root: Path, config: dict[str, Any]) -> int:
    """Copy clauses to .governance/clauses/ with placeholder substitution.

    Phase 1.4 substitution: only `如君所愿` -> config["ritual_phrase"].
    Phase 2 will add more (agent enums, paths, etc.) — but those tools are
    refactored individually to read from config at runtime, not via clause
    text substitution.
    """
    src = PKG_ROOT / "clauses"
    dst = project_root / CLAUSES_REL
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    ritual = config.get("ritual_phrase", "Acknowledged")
    for s in src.glob("art_*.md"):
        dst_file = dst / s.name
        # Mixed clauses are business-owned (P-0063 方案 A): render a generic
        # stub on first install, but never overwrite an existing copy.
        if s.name in MIXED_CLAUSES and dst_file.exists():
            continue
        content = s.read_text(encoding="utf-8")
        content = content.replace("如君所愿", ritual)
        dst_file.write_text(content, encoding="utf-8")
        n += 1
    return n


def _configure_gitattributes(project_root: Path) -> None:
    """Append the per-branch agent.md merge=ours driver to .gitattributes."""
    ga = project_root / ".gitattributes"
    rule_line = "constitution/agent.md merge=ours"
    existing = ga.read_text(encoding="utf-8") if ga.exists() else ""
    if rule_line in existing:
        logger.info("[gitattr] already configured")
        return
    if existing and not existing.endswith("\n"):
        existing += "\n"
    new_content = existing + (
        "\n# governance-core: per-branch agent.md isolation via merge=ours driver\n"
        + rule_line + "\n"
    )
    ga.write_text(new_content, encoding="utf-8")
    logger.info("[gitattr] appended merge=ours rule")
    # Try to enable the driver locally (best-effort)
    try:
        subprocess.run(
            ["git", "config", "merge.ours.driver", "true"],
            cwd=project_root, check=False, capture_output=True,
        )
    except FileNotFoundError:
        pass


def _seed_state_md(project_root: Path, config: dict[str, Any]) -> None:
    """Seed an initial STATE.md if the project has none (P-0068 Phase 3c).

    STATE.md is the session-state bridge maintained by /wrap-up Step 1 and
    rotated by tools/rotate_state.py. An existing STATE.md is never
    overwritten -- it holds the project's real entries.
    """
    state_path = project_root / "STATE.md"
    if state_path.exists():
        return
    project = config["project_name"]
    state_path.write_text(
        f"# STATE -- {project}\n\n"
        "Session-bridge log. `/wrap-up` Step 1 prepends a dated entry under\n"
        '"Updates in This Session"; `tools/rotate_state.py` archives entries\n'
        "older than 7 days to `STATE_ARCHIVE.md`.\n\n"
        "## 1. Updates in This Session\n\n"
        "<!-- Newest entry on top. Format:\n"
        "### YYYY-MM-DD -- <short title>\n"
        "- summary / files / key decisions / test results\n"
        "-->\n",
        encoding="utf-8",
    )
    logger.info("[state] seeded initial STATE.md")


# --- Hook auto-wiring (P-0067) ----------------------------------------------

HOOKS_MANIFEST_REL = "hooks/hooks_manifest.json"
MANAGED_MARKER = "governance-core"
HOOK_COMMAND_TIMEOUT_SEC = 15


def _load_hooks_manifest() -> dict[str, Any]:
    """Load the package hook manifest: hook filename -> {event, matcher}."""
    path = PKG_ROOT / HOOKS_MANIFEST_REL
    return json.loads(path.read_text(encoding="utf-8"))["hooks"]


def _build_hooks_block(manifest_hooks: dict[str, Any]) -> dict[str, Any]:
    """Build the settings.local.json `hooks` block from the hook manifest.

    `manifest_hooks` maps hook filename -> {"event": str, "matcher": str|None}.
    Returns {event: [group, ...]}; each group is tagged
    `"_managed": MANAGED_MARKER` so install/upgrade can regenerate only the
    governance-owned region without touching a project's own hook groups
    (P-0067). Command paths use ${CLAUDE_PROJECT_DIR} for portability.
    """
    by_key: dict[tuple[str, Any], list[str]] = {}
    for fname in sorted(manifest_hooks):
        meta = manifest_hooks[fname]
        by_key.setdefault((meta["event"], meta["matcher"]), []).append(fname)
    block: dict[str, Any] = {}
    for event, matcher in sorted(by_key, key=lambda k: (k[0], k[1] or "")):
        group: dict[str, Any] = {}
        if matcher is not None:
            group["matcher"] = matcher
        group["_managed"] = MANAGED_MARKER
        group["hooks"] = [
            {
                "type": "command",
                "command": f'python "${{CLAUDE_PROJECT_DIR}}/.claude/hooks/{fn}"',
                "timeout": HOOK_COMMAND_TIMEOUT_SEC,
            }
            for fn in by_key[(event, matcher)]
        ]
        block.setdefault(event, []).append(group)
    return block


def _hook_file_of(hook_entry: dict[str, Any]) -> str:
    """Extract the hook filename from a settings hook entry's command."""
    cmd = hook_entry["command"] if "command" in hook_entry else ""
    tail = cmd.rsplit("/hooks/", 1)
    return tail[1].strip().strip('"') if len(tail) == 2 else ""


def _merge_hooks_block(existing_hooks: dict[str, Any],
                       governance_block: dict[str, Any],
                       managed_files: Any) -> dict[str, Any]:
    """Merge the governance hooks block into an existing `hooks` dict.

    A group is governance-owned — and therefore regenerated — if it is
    `_managed`-tagged, OR every hook in it points at a manifest hook file.
    The second rule recognizes a pre-P-0067 hand-authored governance group
    so `upgrade` migrates it (drop + regenerate) instead of duplicating it.
    A project's own groups (pointing at non-manifest hooks) are preserved
    (P-0067 merge-not-clobber). Returns the merged `hooks` dict.
    """
    managed_files = set(managed_files)

    def _is_governance(g: Any) -> bool:
        if not isinstance(g, dict):
            return False
        if g.get("_managed") == MANAGED_MARKER:
            return True
        hooks = g["hooks"] if "hooks" in g else []
        if not hooks:
            return False
        return all(_hook_file_of(h) in managed_files for h in hooks)

    merged: dict[str, Any] = {}
    for event, groups in existing_hooks.items():
        kept = [g for g in groups if not _is_governance(g)]
        if kept:
            merged[event] = kept
    for event, groups in governance_block.items():
        merged.setdefault(event, []).extend(groups)
    return merged


def _write_settings_local_json(project_root: Path) -> None:
    """Write or merge .claude/settings.local.json with the governance hooks.

    Fresh project: create the file with the generated governance hook block.
    Existing file: regenerate only the `_managed: governance-core` groups,
    preserving the project's own hook groups. settings.local.json is a
    critical path an interactive agent cannot write directly; the installer
    runs as a subprocess and is the correct actor to wire hooks (P-0067).
    """
    settings_path = project_root / CLAUDE_DIR / "settings.local.json"
    manifest = _load_hooks_manifest()
    governance_block = _build_hooks_block(manifest)
    if settings_path.exists():
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        existing_hooks = data["hooks"] if "hooks" in data else {}
        data["hooks"] = _merge_hooks_block(existing_hooks, governance_block, manifest)
    else:
        data = {
            "_comment": (
                "Hook registrations are generated by governance-core "
                "install/upgrade from hooks/hooks_manifest.json. Groups "
                'tagged "_managed": "governance-core" are regenerated on '
                "every upgrade; add your own hook groups WITHOUT that tag "
                "and they are preserved."
            ),
            "hooks": governance_block,
        }
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n = sum(len(g["hooks"]) for groups in governance_block.values() for g in groups)
    logger.info("[settings] wrote settings.local.json (%d governance hooks)", n)


def install(
    project_root: Path,
    config_overrides: dict[str, Any] | None = None,
    preserve_config: bool = False,
    force: bool = False,
) -> int:
    project_root = project_root.resolve()
    if not project_root.exists():
        logger.error("[install] project root does not exist: %s", project_root)
        return 1

    config_overrides = config_overrides or {}
    cfg = _load_or_init_config(project_root, config_overrides, preserve_config)
    logger.info("[install] project=%s ritual_phrase=%r", cfg.get("project_name"), cfg.get("ritual_phrase"))

    counts = {}
    for src_sub, dst_sub in COPY_CATEGORIES:
        src = PKG_ROOT / src_sub
        dst = project_root / dst_sub
        n = _copy_tree(src, dst)
        counts[f".claude/{src_sub}" if src_sub != "tools" and src_sub != "contracts" and src_sub != "agent_rules" else dst_sub] = n
    for src_sub, dst_sub in KNOWLEDGE_COPY_MAP:
        src = PKG_ROOT / src_sub
        dst = project_root / dst_sub
        # Only copy top-level files of the package subdir; skip recursive nesting
        # of methodology/design/operations (since they live under knowledge_governance/)
        n = 0
        if src.exists():
            for s in src.iterdir():
                if s.is_file() and s.name != "README.md":
                    d = dst / s.name
                    d.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(s, d)
                    n += 1
        counts[dst_sub] = n

    n_clauses = _render_clauses(project_root, cfg)
    counts[".governance/clauses"] = n_clauses

    _configure_gitattributes(project_root)
    _seed_state_md(project_root, cfg)
    _write_settings_local_json(project_root)

    logger.info("[install] complete. Files installed:")
    for k, v in counts.items():
        logger.info("  %-30s %d", k, v)

    return 0


def doctor(project_root: Path) -> int:
    project_root = project_root.resolve()
    cfg_path = project_root / CONFIG_REL
    if not cfg_path.exists():
        logger.error("[doctor] no .governance/config.json at %s", project_root)
        return 1
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.error("[doctor] invalid config.json: %s", e)
        return 2
    required_keys = ["project_name", "install_root", "shared_state_root",
                     "core_agent_name", "ritual_phrase", "agents"]
    missing = [k for k in required_keys if k not in cfg]
    if missing:
        logger.error("[doctor] missing config keys: %s", missing)
        return 3
    # Check hooks installed
    hooks_dir = project_root / ".claude" / "hooks"
    if not hooks_dir.exists() or not list(hooks_dir.glob("*.py")):
        logger.error("[doctor] no hooks in .claude/hooks/")
        return 4
    # Check clauses installed
    clauses_dir = project_root / CLAUSES_REL
    if not clauses_dir.exists() or not list(clauses_dir.glob("art_*.md")):
        logger.error("[doctor] no clauses in .governance/clauses/")
        return 5
    # P-0067: verify every shipped hook is registered in settings.local.json
    settings_path = project_root / CLAUDE_DIR / "settings.local.json"
    if not settings_path.exists():
        logger.error("[doctor] no %s/settings.local.json (run install)", CLAUDE_DIR)
        return 6
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    settings_hooks = settings["hooks"] if "hooks" in settings else {}
    registered = set()
    for groups in settings_hooks.values():
        for g in groups:
            for h in g["hooks"]:
                registered.add(_hook_file_of(h))
    unregistered = sorted(set(_load_hooks_manifest()) - registered)
    if unregistered:
        logger.error("[doctor] hooks installed but not registered in "
                      "settings.local.json: %s", unregistered)
        return 6
    logger.info("[doctor] OK: project=%s ritual_phrase=%r agents=%d hooks=%d "
                "clauses=%d hooks_registered=%d",
                cfg["project_name"], cfg["ritual_phrase"], len(cfg["agents"]),
                len(list(hooks_dir.glob("*.py"))),
                len(list(clauses_dir.glob("art_*.md"))),
                len(registered))
    return 0


def render_clauses(out_dir: Path, project_root: Path) -> int:
    project_root = project_root.resolve()
    cfg_path = project_root / CONFIG_REL
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    else:
        cfg = DEFAULT_CONFIG
    out_dir.mkdir(parents=True, exist_ok=True)
    src = PKG_ROOT / "clauses"
    ritual = cfg.get("ritual_phrase", "Acknowledged")
    n = 0
    for s in src.glob("art_*.md"):
        content = s.read_text(encoding="utf-8").replace("如君所愿", ritual)
        (out_dir / s.name).write_text(content, encoding="utf-8")
        n += 1
    logger.info("[render] %d clauses -> %s", n, out_dir)
    return 0
