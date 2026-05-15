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
    logger.info("[doctor] OK: project=%s ritual_phrase=%r agents=%d hooks=%d clauses=%d",
                cfg["project_name"], cfg["ritual_phrase"], len(cfg["agents"]),
                len(list(hooks_dir.glob("*.py"))),
                len(list(clauses_dir.glob("art_*.md"))))
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
