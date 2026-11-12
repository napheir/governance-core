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

import datetime
import difflib
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from governance_core.auth import codec
from governance_core.auth import store as auth_store

logger = logging.getLogger("governance_core.installer")

# P-0065 Phase 1: candidate-uplink consent terms version. Bumping this on a
# future terms change makes upgrade re-prompt for consent.
CONSENT_TERMS_VERSION = 1

# Package root (path to governance_core/ directory)
PKG_ROOT = Path(__file__).resolve().parent

CONFIG_REL = ".governance/config.json"
CLAUSES_REL = ".governance/clauses"
INSTALLED_FILES_REL = ".governance/installed_files.json"
# Consumer-owned (P-0117, #119): declares install-managed files the consumer has
# intentionally + permanently diverged, so _capture_drift stamps them layer:business
# (sweep skips non-common) instead of re-uplinking them every upgrade. NOT in
# installed_files.json -- upgrade never clobbers it.
INTENTIONAL_DRIFT_REL = ".governance/intentional_drift.json"
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
    # P-0082: vendor the auth subpackage beside auth-guard so the hook is
    # self-contained (no `import governance_core`). Same source, copied.
    ("auth",      ".claude/hooks/_gc_auth"),
]

# P-0065 Phase 2: copy-category source subdir -> installed_files.json
# category. Clause and knowledge files are tagged inline in install().
CATEGORY_OF = {
    "hooks": "hook",
    "skills": "skill",
    "commands": "command",
    "agents": "agent",
    "contracts": "contract",
    "agent_rules": "agent_rule",
    "tools": "tool",
    "auth": "auth",
}

KNOWLEDGE_COPY_MAP = [
    ("knowledge_governance", "knowledge/governance"),
    ("knowledge_governance/methodology", "knowledge/methodology"),
    ("knowledge_governance/operations", "knowledge/operations"),
]

# P-0075: paths released from install-management to business ownership at the
# 0.6.0 -> 0.7.0 boundary. _prune_stale skips them so a consumer that received
# the residual dashboard/HK-trading design files in 0.5.0/0.6.0 keeps them as
# business carve-out after upgrading. The set is one-shot and self-decaying:
# after the upgrade that crosses the 0.7.0 line, the released paths drop out
# of installed_files.json (the new install set has no source for them), so
# subsequent prunes never look at them again. Safe to delete this set in a
# future major version once all known consumers have crossed 0.7.0.
STALE_PRUNE_EXEMPT = {
    "knowledge/design/component-catalog.md",
    "knowledge/design/design-principles.md",
    ".claude/agents/design-system-owner.md",
    # gc #24 (P-0091): the knowledge-RENDERING tools are the consumer's, not
    # gc's (gc owns governance content / contracts / validators / taxonomy, not
    # how a project renders its knowledge). Released from install-management; a
    # consumer that already has them keeps them as business-owned carve-out.
    "tools/build_knowledge_dashboard.py",
    "tools/build_autogen_blocks.py",
    ".claude/commands/dashboard.md",
}

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
    """Load .governance/config.json (or seed DEFAULT_CONFIG); merge overrides.

    Does NOT persist -- install() writes the config exactly once, after the
    authorization + consent gate (P-0065 Phase 1), so a failed gate never
    leaves a half-configured project behind.
    """
    cfg_path = project_root / CONFIG_REL
    if cfg_path.exists():
        existing = json.loads(cfg_path.read_text(encoding="utf-8"))
        if preserve_config:
            return existing
    else:
        existing = DEFAULT_CONFIG.copy()
    # Shallow merge overrides
    for k, v in config_overrides.items():
        existing[k] = v
    return existing


def _write_config(project_root: Path, config: dict[str, Any]) -> None:
    """Persist `config` to .governance/config.json."""
    cfg_path = project_root / CONFIG_REL
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("[config] wrote %s", cfg_path)


# --- Authorization + consent gate (P-0065 Phase 1) --------------------------


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 'Z' string."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _legacy_config_code(config: dict[str, Any]) -> str | None:
    """Return the pre-P-0132 code stored in config.json, or None."""
    if ("authorization" in config and isinstance(config["authorization"], dict)
            and "auth_code" in config["authorization"]):
        return config["authorization"]["auth_code"]
    return None


def _resolve_auth_code(project_root: Path, config: dict[str, Any],
                       auth_code_arg: str | None) -> tuple[str | None, str]:
    """Return (code, source): the CLI arg, else the code file, else config.

    config.json's `authorization.auth_code` is read only as a migration
    source when `.governance/auth_code` does not exist yet (P-0132), so an
    upgrade never strands a clone without its code.
    """
    if auth_code_arg:
        return auth_code_arg, "--auth-code"
    stored = auth_store.read_code(project_root)
    if stored:
        return stored, auth_store.AUTH_CODE_REL
    legacy = _legacy_config_code(config)
    if legacy:
        return legacy, f"{CONFIG_REL} (migrating to {auth_store.AUTH_CODE_REL})"
    return None, ""


def _install_time_revocation(code: str, payload: dict[str, Any]) -> str:
    """Best-effort revocation check at install; return a reason if revoked.

    Fetches the signed feed named in a schema-2 code once (short timeout)
    and verifies it with the bundled key. "" when the code is not revoked,
    the code carries no feed, or the feed cannot be fetched / verified --
    the runtime auth-guard enforces revocation either way (P-0132).
    """
    if "revocation_feed_url" not in payload:
        return ""
    from governance_core.auth import revocation
    feed_url = payload["revocation_feed_url"]
    try:
        with urllib.request.urlopen(feed_url, timeout=8) as resp:
            feed_bytes = resp.read()
        with urllib.request.urlopen(revocation.sig_url_for(feed_url),
                                    timeout=8) as resp:
            sig_text = resp.read().decode("utf-8")
        feed = revocation.verify_feed(feed_bytes, sig_text,
                                      codec.load_bundled_public_key())
    except Exception as exc:  # noqa: BLE001 - offline / bad feed: runtime gate decides
        logger.info("[install] revocation feed not checked (%s); auth-guard "
                    "enforces it at runtime", exc)
        return ""
    if revocation.is_revoked(feed, payload["consumer_id"],
                             codec.code_fingerprint(code)):
        return (f"this authorization code (consumer_id="
                f"{payload['consumer_id']!r}) is on the revocation feed")
    return ""


def _consent_satisfied(config: dict[str, Any]) -> bool:
    """Return True if config already records current-terms uplink consent."""
    if "candidate_uplink" not in config:
        return False
    cu = config["candidate_uplink"]
    return (cu.get("consent") is True
            and cu.get("consent_terms_version") == CONSENT_TERMS_VERSION)


def _collect_consent(config: dict[str, Any], accept_flag: bool) -> bool:
    """Resolve candidate-uplink consent for install/upgrade (P-0065 Phase 1).

    Current version: consent is mandatory -- only an explicit yes lets the
    governance layer materialize. An already-recorded current-terms consent
    carries forward; otherwise the `--accept-candidate-uplink` flag or an
    interactive yes is required. Non-interactive without the flag -> denied.
    """
    if _consent_satisfied(config):
        return True
    if accept_flag:
        return True
    if sys.stdin.isatty():
        logger.info(
            "[consent] Candidate uplink: improved skills / hooks / mechanisms "
            "from this project may be packaged as candidates and uploaded to "
            "governance-core's PUBLIC GitHub repository for review. This "
            "version REQUIRES consent to use the governance layer."
        )
        try:
            answer = input("[consent] Agree to candidate uplink? [y/N] ")
        except (EOFError, KeyboardInterrupt):
            # No usable input -> treat as a denial rather than crashing.
            return False
        return answer.strip().lower() in ("y", "yes")
    return False


def _copy_tree(src: Path, dst: Path, dry_run: bool = False) -> list[Path]:
    """Copy a directory tree; return the destination paths (would be) written.

    Overwrites existing files. Per-category README.md files at the package
    subdir root are skipped (docs, not governance assets). With `dry_run`,
    the destination list is computed identically but nothing is written.
    """
    if not src.exists():
        logger.warning("[copy] source missing: %s", src)
        return []
    written: list[Path] = []
    for s in src.rglob("*"):
        if s.is_dir():
            continue
        if "__pycache__" in s.parts or s.suffix == ".pyc":
            continue  # never copy bytecode (e.g. when vendoring auth/, P-0082)
        if s.name == "README.md" and s.parent == src:
            # Skip per-category READMEs in the package (they're just docs)
            continue
        rel = s.relative_to(src)
        d = dst / rel
        if not dry_run:
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, d)
        written.append(d)
    return written


def _is_business_owned_clause(rel: str) -> bool:
    """Return True if repo-relative POSIX `rel` is a mixed clause (P-0063 A).

    Mixed clauses belong to the project from birth: they are never recorded
    in installed_files.json, never drift-captured and never pruned (P-0129 F2).
    """
    prefix = CLAUSES_REL + "/"
    return rel.startswith(prefix) and rel[len(prefix):] in MIXED_CLAUSES


def _render_clauses(project_root: Path, config: dict[str, Any],
                    dry_run: bool = False) -> tuple[list[Path], list[Path]]:
    """Copy clauses to .governance/clauses/ with placeholder substitution.

    Substitution: `如君所愿` -> config ritual_phrase. Returns
    (managed, seeded): `managed` are install-managed clauses (recorded in
    the manifest, overwritten on every install); `seeded` are mixed clauses
    (P-0063 方案 A) rendered as a generic stub only when absent. Seeded
    files are business-owned from birth and are NOT recorded in the manifest
    -- recording them made the next install, which skips the existing copy,
    prune them as stale (P-0129 F2).
    """
    src = PKG_ROOT / "clauses"
    dst = project_root / CLAUSES_REL
    if not dry_run:
        dst.mkdir(parents=True, exist_ok=True)
    managed: list[Path] = []
    seeded: list[Path] = []
    for s in src.glob("art_*.md"):
        dst_file = dst / s.name
        is_mixed = s.name in MIXED_CLAUSES
        if is_mixed and dst_file.exists():
            continue  # the project's copy -- never overwritten
        if not dry_run:
            dst_file.write_text(_rendered_clause(s, config), encoding="utf-8")
        (seeded if is_mixed else managed).append(dst_file)
    return managed, seeded


def _rendered_clause(src: Path, config: dict[str, Any]) -> str:
    """Return the text install writes for package clause `src`.

    `如君所愿` is replaced by config ritual_phrase. Shared by _render_clauses
    and the drift check (_incoming_sha256), so both see the same content.
    """
    ritual = (config["ritual_phrase"] if "ritual_phrase" in config
              else "Acknowledged")
    return src.read_text(encoding="utf-8").replace("如君所愿", ritual)


def _incoming_sha256(rel_posix: str, config: dict[str, Any]) -> str | None:
    """Return the _content_sha256 of what this install writes to `rel_posix`.

    Copied files are byte copies of their package source; generic clauses
    are rendered. Returns None for a path with no package source.
    """
    src = _pkg_source_path(rel_posix)
    if src is None or not src.is_file():
        return None
    if rel_posix.startswith(CLAUSES_REL + "/"):
        return _lf_sha256(_rendered_clause(src, config).encode("utf-8"))
    return _content_sha256(src)


def _lf_sha256(data: bytes) -> str:
    """SHA-256 of `data` with line endings normalized to LF (see below)."""
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _content_sha256(path: Path) -> str:
    """SHA-256 of a file's content with line endings normalized to LF.

    Install-managed files are text; a consumer on core.autocrlf=true checks
    them out as CRLF while the package materializes LF, so a raw-byte hash
    reports spurious drift on every file. Normalizing CRLF/CR -> LF before
    hashing makes drift detection line-ending-insensitive: a file that differs
    only by EOL is not a local edit. Genuine content edits still change the hash.

    Both the manifest baseline (_write_installed_manifest) and the drift-check
    (_capture_drift) MUST use this same helper -- an asymmetry would reintroduce
    the mismatch. Promoted from candidate gc #27 (P-0094).
    """
    return _lf_sha256(path.read_bytes())


def _write_installed_manifest(project_root: Path,
                              installed: list[tuple[Path, str]]) -> None:
    """Write .governance/installed_files.json (P-0065 Phase 2).

    Records every install-managed file materialized this run: project-root
    relative POSIX path, content sha256 baseline, source governance-core
    version, and category. The manifest answers "is this path install-managed
    or business?" (membership) and is the baseline for drift detection
    (later P-0065 phases).
    """
    from governance_core import __version__
    files = []
    for dest_path, category in installed:
        if not dest_path.exists():
            continue
        files.append({
            "path": dest_path.relative_to(project_root).as_posix(),
            "baseline_sha256": _content_sha256(dest_path),
            "source_version": __version__,
            "category": category,
        })
    files.sort(key=lambda f: f["path"])
    manifest = {
        "schema": 1,
        "governance_core_version": __version__,
        "generated_at": _now_iso(),
        "files": files,
    }
    manifest_path = project_root / INSTALLED_FILES_REL
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("[manifest] wrote installed_files.json (%d files)", len(files))


def _load_intentional_drift(project_root: Path) -> set[str]:
    """Return repo-relative paths a consumer declared as intentional drift.

    Reads the consumer-owned ``.governance/intentional_drift.json`` (schema
    ``{"schema": 1, "drift_targets": ["<repo-relative path>", ...]}``). A drifted
    install-managed file whose path is in this set is stamped ``layer: business``
    by ``_capture_drift`` (so the consumer sweep, which acts only on
    ``candidate-common``, skips it) instead of being re-uplinked as a candidate on
    every upgrade (P-0117, #119).

    Fail-safe: missing / malformed / wrong-schema -> empty set. The file is
    advisory noise-suppression, never a correctness gate, so a bad file must not
    break upgrade. Paths are normalized to forward slashes for matching against
    manifest entries. Uses explicit membership tests (no dict fallback-default,
    per Art.4).
    """
    path = project_root / INTENTIONAL_DRIFT_REL
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[drift] ignoring malformed %s: %s",
                       INTENTIONAL_DRIFT_REL, exc)
        return set()
    if (not isinstance(data, dict) or "schema" not in data
            or data["schema"] != 1):
        logger.warning("[drift] %s has unexpected schema; ignoring",
                       INTENTIONAL_DRIFT_REL)
        return set()
    targets = data["drift_targets"] if "drift_targets" in data else []
    if not isinstance(targets, list):
        return set()
    return {str(t).replace("\\", "/") for t in targets if isinstance(t, str)}


def _capture_drift(project_root: Path, consumer_id: str,
                   config: dict[str, Any],
                   dry_run: bool = False) -> list[str]:
    """Capture locally-edited install-managed files as drift candidates.

    Before upgrade overwrites the autonomy layer, each install-managed file
    whose content matches neither its installed_files.json baseline nor what
    this install is about to write is a local edit. It is packaged as a
    `drift` candidate envelope in the outbox -- so the edit is preserved as a
    reviewable candidate -- and then left for the normal copy to overwrite
    (capture, then overwrite: no silent fork; P-0065 Phase 4). Returns the
    list of drifted paths.

    A file already equal to the incoming version is not drift. In a
    multi-clone project a business clone receives the gc-managed files that
    core committed through a git merge, while its untracked manifest still
    holds the previous version's baselines.
    """
    from governance_core.candidates import collect, envelope
    manifest_path = project_root / INSTALLED_FILES_REL
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    outbox = collect.outbox_dir(project_root)
    drifted: list[str] = []
    # P-0117 (#119): consumer-declared intentional drift is captured but stamped
    # layer:business so the candidate-common-only sweep skips it (no recurring
    # hub uplink of the same permanent divergence).
    intentional = _load_intentional_drift(project_root)
    for entry in manifest["files"]:
        path = project_root / entry["path"]
        if not path.exists():
            continue
        if _is_business_owned_clause(entry["path"]):
            # P-0129 F2: a pre-0.46 manifest recorded mixed clauses; the
            # project's edits to them are its own content, not drift to uplink.
            continue
        current = _content_sha256(path)
        if current == entry["baseline_sha256"]:
            continue
        if current == _incoming_sha256(entry["path"], config):
            continue  # e.g. merged in from core: what upgrade writes anyway
        drifted.append(entry["path"])
        if dry_run:
            continue  # dry-run: detect drift, do not build envelopes
        category = entry["category"]
        kind = category if category in ("hook", "skill") else "mechanism"
        drift_layer = ("business"
                       if entry["path"].replace("\\", "/") in intentional
                       else "candidate-common")
        try:
            envelope.build_envelope(
                outbox,
                kind=kind,
                origin=consumer_id,
                title=f"drift {Path(entry['path']).name}",
                rationale=(f"install-managed file locally edited: "
                           f"{entry['path']}"),
                payload_files=[path],
                layer=drift_layer,
                drift_target=entry["path"],
                baseline_sha256=entry["baseline_sha256"],
            )
        except envelope.EnvelopeError as exc:
            logger.warning("[drift] could not capture %s: %s",
                           entry["path"], exc)
    return drifted


def _prune_stale(project_root: Path,
                 installed: list[tuple[Path, str]],
                 dry_run: bool = False) -> list[str]:
    """Delete autonomy-layer files dropped from the package source (P-0070).

    Compares the *previous* installed_files.json against the set just
    materialized: a path the old manifest recorded as install-managed but
    that the new install no longer produces is a stale file (its package
    source was removed) and is deleted.

    Manifest-diff is the safety boundary -- only paths the old manifest
    recorded as install-managed are eligible. Business files, authored
    files, and the `.claude/skills/learned/` carve-out are never in the
    manifest, so are never pruned. Prune runs *after* `_capture_drift`, so a
    stale file the consumer had locally edited is first captured as a drift
    candidate, then removed -- no silent loss. Returns the pruned paths.
    """
    manifest_path = project_root / INSTALLED_FILES_REL
    if not manifest_path.exists():
        return []
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    new_paths = {p.relative_to(project_root).as_posix() for p, _ in installed}
    pruned: list[str] = []
    touched_dirs: set[Path] = set()
    for entry in old["files"]:
        rel = entry["path"]
        if rel in new_paths:
            continue
        if rel in STALE_PRUNE_EXEMPT or _is_business_owned_clause(rel):
            # P-0075: released to business ownership at the 0.7.0 boundary.
            # P-0129 F2: a mixed clause recorded by a pre-0.46 install is the
            # project's file, not a stale one. Either way the file stays on
            # disk and the new manifest omits it, so future prunes never look
            # at this path again.
            logger.info("[prune] released to business ownership: %s", rel)
            continue
        target = project_root / rel
        if not target.exists():
            continue  # already gone
        if dry_run:
            pruned.append(rel)
            continue  # dry-run: compute the prune set, delete nothing
        try:
            target.unlink()
            pruned.append(rel)
            touched_dirs.add(target.parent)
        except OSError as exc:
            logger.warning("[prune] could not remove %s: %s", rel, exc)
    # Remove directories left empty by pruning.
    for directory in touched_dirs:
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            pass
    return pruned


# P-0129 F10: runtime state written by the governance hooks / tools. Kept as
# a marker-delimited block in the consumer's .gitignore; the installer owns
# only the lines between the markers.
GITIGNORE_BLOCK_BEGIN = "# >>> governance-core runtime (managed by governance-core install) >>>"
GITIGNORE_BLOCK_END = "# <<< governance-core runtime <<<"
GITIGNORE_RUNTIME_PATTERNS = (
    "/.claude/cache/",
    "/.claude/skills/learned/.usage.json",
    "/.claude/hooks/.direction_check_ts",
    "/.claude/settings.local.json",
    "/audit/",
    "/.governance/installed_files.json",
    "/.governance/candidate-outbox/",
    "/.governance/state_seen.json",
    "/.governance/pending_writes/",
    "/.governance/notice_gate_seen.json",
)
# P-0132: the authorization code file. Ignored by default; a private repo
# that wants every clone to receive it through git re-includes it with
# `!/.governance/auth_code` below the block (lines outside the block are
# the owner's). Kept apart from the runtime patterns so doctor's
# "runtime files still tracked" note does not report a deliberate choice.
GITIGNORE_SECRET_PATTERNS = ("/" + auth_store.AUTH_CODE_REL,)


def _update_gitignore_text(existing: str) -> str | None:
    """Return `existing` with the managed runtime block replaced or appended.

    The block uses the file's own line ending (CRLF if present, else LF), and
    every byte outside the markers is preserved. Returns None when a begin
    marker has no end marker -- a hand-damaged block is left for a human
    rather than guessed at.
    """
    eol = "\r\n" if "\r\n" in existing else "\n"
    block = eol.join([
        GITIGNORE_BLOCK_BEGIN,
        "# Runtime state written by governance hooks / tools -- never commit.",
        *GITIGNORE_RUNTIME_PATTERNS,
        "# Authorization code (secret). A PRIVATE repo may re-include it with",
        "# !/.governance/auth_code after this block.",
        *GITIGNORE_SECRET_PATTERNS,
        GITIGNORE_BLOCK_END,
    ]) + eol
    start = existing.find(GITIGNORE_BLOCK_BEGIN)
    if start != -1:
        end = existing.find(GITIGNORE_BLOCK_END, start)
        if end == -1:
            return None
        line_end = existing.find("\n", end)
        stop = len(existing) if line_end == -1 else line_end + 1
        return existing[:start] + block + existing[stop:]
    if not existing:
        return block
    sep = "" if existing.endswith("\n") else eol
    return existing + sep + eol + block


def _configure_gitignore(project_root: Path) -> None:
    """Ensure .gitignore carries the current managed runtime block (F10)."""
    path = project_root / ".gitignore"
    existing = ""
    if path.exists():
        with open(path, encoding="utf-8", newline="") as f:
            existing = f.read()
    updated = _update_gitignore_text(existing)
    if updated is None:
        logger.warning("[gitignore] '%s' marker without '%s' -- managed block "
                       "left unchanged; repair it by hand",
                       GITIGNORE_BLOCK_BEGIN, GITIGNORE_BLOCK_END)
        return
    if updated == existing:
        logger.info("[gitignore] runtime block up to date")
        return
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(updated)
    logger.info("[gitignore] runtime block written")


def _git_tracks(project_root: Path, rel: str) -> bool:
    """Return True when git tracks `rel` in `project_root` (best-effort)."""
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "ls-files", "--error-unmatch",
             "--", rel],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0


def _tracked_runtime_files(project_root: Path) -> list[str]:
    """Return runtime-state paths that git still tracks (best-effort).

    .gitignore does not untrack files committed before the block existed;
    doctor lists them so the owner can `git rm --cached` them.
    """
    specs = [p.lstrip("/").rstrip("/") for p in GITIGNORE_RUNTIME_PATTERNS]
    try:
        out = subprocess.run(
            ["git", "-C", str(project_root), "ls-files", "-z", "--", *specs],
            capture_output=True, encoding="utf-8", errors="replace",
            timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.split("\0") if p]


# P-0129 F3: session-boundary anchor for multi-clone projects. A clone's
# .claude/settings.json declaring projectRoot "../" makes session-boundary-guard
# use the project directory (all clones + shared_state/) as the boundary, so
# proposals in ../shared_state/ are writable without CLAUDE_BOUNDARY_OVERRIDE.
# Safe only because agent identity is config-derived (Phase A): the wider
# boundary does not widen what a business agent's guards allow.
BOUNDARY_ANCHOR_KEY = "projectRoot"
BOUNDARY_ANCHOR_VALUE = "../"


def _boundary_anchor_wanted(project_root: Path, config: dict[str, Any]) -> bool:
    """Return True for a multi-clone layout: >1 agent, shared_state is a sibling.

    The anchor is only meaningful when the clones and shared_state_root sit
    in the same project directory (<project>/<clone>, <project>/shared_state).
    Single-agent projects and non-standard layouts get no anchor.
    """
    if "agents" not in config or len(config["agents"]) < 2:
        return False
    if "shared_state_root" not in config:
        return False
    shared_parent = Path(config["shared_state_root"]).resolve().parent
    return (os.path.normcase(str(shared_parent))
            == os.path.normcase(str(project_root.resolve().parent)))


def _ensure_boundary_anchor(project_root: Path, config: dict[str, Any]) -> None:
    """Idempotently add projectRoot "../" to .claude/settings.json (F3).

    Only the one key is added; every other key is kept. An existing
    projectRoot with another value is the owner's choice and is left alone
    (logged). An unparseable settings.json is never rewritten.
    """
    if not _boundary_anchor_wanted(project_root, config):
        return
    path = project_root / CLAUDE_DIR / "settings.json"
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[boundary] %s unreadable (%s); projectRoot anchor "
                           "not written", path, exc)
            return
        if not isinstance(data, dict):
            logger.warning("[boundary] %s is not a JSON object; projectRoot "
                           "anchor not written", path)
            return
    if BOUNDARY_ANCHOR_KEY in data:
        if data[BOUNDARY_ANCHOR_KEY] != BOUNDARY_ANCHOR_VALUE:
            logger.warning("[boundary] %s declares %s=%r (expected %r); left "
                           "unchanged", path, BOUNDARY_ANCHOR_KEY,
                           data[BOUNDARY_ANCHOR_KEY], BOUNDARY_ANCHOR_VALUE)
        else:
            logger.info("[boundary] projectRoot anchor up to date")
        return
    data[BOUNDARY_ANCHOR_KEY] = BOUNDARY_ANCHOR_VALUE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    logger.info("[boundary] wrote projectRoot anchor to %s", path)


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


# P-0129 F4: a fresh project gets a real total constitution -- one summary +
# pointer per generic clause -- so CLAUDE.md is not an empty stub and the
# clauses reach the agent's context. Seeded only when absent; project-owned.
CONSTITUTION_TEMPLATE = PKG_ROOT / "default_config" / "constitution_total.md.template"
REGEN_BANNER_PREFIX = "<!-- AUTO-GENERATED by tools/regen_constitution.py"


def _render_constitution_total(config: dict[str, Any]) -> str:
    """Render the total-constitution template for this project's config."""
    rows = ["> | Agent | 分支 | Clone 目录 |", "> |---|---|---|"]
    for agent in config["agents"]:
        branch = f"`{agent['branch']}`" if "branch" in agent else "-"
        core_mark = "（core）" if agent["name"] == config["core_agent_name"] else ""
        rows.append(f"> | `{agent['name']}`{core_mark} | {branch} | "
                    f"`{agent['clone_dir']}/` |")
    text = CONSTITUTION_TEMPLATE.read_text(encoding="utf-8")
    return (text.replace("{{PROJECT_NAME}}", config["project_name"])
                .replace("{{RITUAL_PHRASE}}", config["ritual_phrase"])
                .replace("{{AGENT_TABLE}}", "\n".join(rows)))


def _regen_claude_md(project_root: Path) -> None:
    """Generate CLAUDE.md with the project's installed regen_constitution.

    Uses the same build path as `python tools/regen_constitution.py`, so a
    following `--check` reports in sync. Identity failure (regen exits) is
    logged, not raised: install must not fail on it -- doctor reports it.
    """
    import importlib.util
    tool = project_root / "tools" / "regen_constitution.py"
    if not tool.is_file():
        tool = PKG_ROOT / "tools" / "regen_constitution.py"
    spec = importlib.util.spec_from_file_location("_gc_regen_install", tool)
    regen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(regen)
    try:
        role = regen.detect_role(project_root)
    except SystemExit:
        logger.warning("[constitution] agent identity unresolved; CLAUDE.md "
                       "not generated -- fix config, then run "
                       "python tools/regen_constitution.py")
        return
    total = project_root / "constitution" / "total.md"
    agent_path = regen.resolve_agent_path(project_root, role)
    (project_root / "CLAUDE.md").write_text(
        regen.build_constitution(total, agent_path), encoding="utf-8")
    logger.info("[constitution] generated CLAUDE.md (agent=%s)", role)


def _seed_constitution(project_root: Path, config: dict[str, Any]) -> None:
    """Seed constitution/total.md when absent, then generate CLAUDE.md (F4).

    An existing total.md is never touched. A hand-written CLAUDE.md (no
    regen banner) is never overwritten: its rules belong in total.md first.
    """
    total = project_root / "constitution" / "total.md"
    if total.exists():
        return
    total.parent.mkdir(parents=True, exist_ok=True)
    total.write_text(_render_constitution_total(config), encoding="utf-8")
    logger.info("[constitution] seeded constitution/total.md")
    claude_md = project_root / "CLAUDE.md"
    if (claude_md.exists() and not claude_md.read_text(encoding="utf-8")
            .startswith(REGEN_BANNER_PREFIX)):
        logger.warning("[constitution] existing CLAUDE.md was not generated by "
                       "regen_constitution; left unchanged -- move its project "
                       "rules into constitution/total.md, then run "
                       "python tools/regen_constitution.py")
        return
    _regen_claude_md(project_root)


# P-0129 F9: commit-time scope gate. Each non-core agent gets a seeded (empty,
# commented) allow list -- business-owned, never in the manifest -- and every
# clone gets a pre-commit stub that runs tools/check_scope.py --staged-only,
# plus a pre-merge-commit stub: an automatic merge commit runs no pre-commit.
ALLOW_SEED_TEMPLATE = (
    "# Write scope for agent '{agent}' (seeded by governance-core install, P-0129).\n"
    "# One repo-relative path prefix per line, e.g.  services/api/\n"
    "# Lines starting with '#' are comments. An empty list allows nothing:\n"
    "# edit-write-guard blocks every write outside .claude/ and shared_state/,\n"
    "# and the pre-commit gate rejects every staged file.\n"
    "# Maintained by the core agent ('{core}'); changes go through /proposal.\n"
)
PRE_COMMIT_TEMPLATE = PKG_ROOT / "default_config" / "pre-commit.template"
PRE_COMMIT_MARKER = "# governance-core pre-commit gate"
PRE_MERGE_COMMIT_TEMPLATE = PKG_ROOT / "default_config" / "pre-merge-commit.template"
PRE_MERGE_COMMIT_MARKER = "# governance-core pre-merge-commit gate"
# (git hook name, stub template, ownership marker, what a foreign hook must run)
COMMIT_GATES = (
    ("pre-commit", PRE_COMMIT_TEMPLATE, PRE_COMMIT_MARKER,
     "python tools/check_scope.py --staged-only"),
    ("pre-merge-commit", PRE_MERGE_COMMIT_TEMPLATE, PRE_MERGE_COMMIT_MARKER,
     "python tools/check_scope.py --merge-commit"),
)


def _seed_allow_lists(project_root: Path, config: dict[str, Any]) -> list[str]:
    """Seed agent_rules/<agent>.allow.txt for each non-core agent if absent.

    Returns the agent names seeded. The core agent has no allow list (no
    scope restriction). Existing files are never touched.
    """
    seeded = []
    rules_dir = project_root / "agent_rules"
    for agent in config["agents"]:
        name = agent["name"]
        if name == config["core_agent_name"]:
            continue
        allow = rules_dir / f"{name}.allow.txt"
        if allow.exists():
            continue
        rules_dir.mkdir(parents=True, exist_ok=True)
        allow.write_text(ALLOW_SEED_TEMPLATE.format(
            agent=name, core=config["core_agent_name"]), encoding="utf-8")
        seeded.append(name)
    if seeded:
        logger.info("[scope] seeded empty allow lists (deny-all) for: %s -- "
                    "core must fill them", seeded)
    return seeded


def _allow_rule_count(project_root: Path, agent: str) -> int:
    """Number of non-comment rules in agent_rules/<agent>.allow.txt (0 if absent)."""
    allow = project_root / "agent_rules" / f"{agent}.allow.txt"
    if not allow.exists():
        return 0
    return sum(1 for line in allow.read_text(encoding="utf-8").splitlines()
               if line.strip() and not line.strip().startswith("#"))


def _git_hooks_dir(project_root: Path) -> Path | None:
    """Return <git-dir>/hooks when project_root is a git work-tree root.

    None when it is not a repo root, git is unavailable, or core.hooksPath is
    set (the owner manages hooks elsewhere -- e.g. a hook framework).
    """
    def _git(*args: str) -> subprocess.CompletedProcess | None:
        try:
            return subprocess.run(["git", "-C", str(project_root), *args],
                                  capture_output=True, encoding="utf-8",
                                  errors="replace", timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
    top = _git("rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0:
        return None
    if (os.path.normcase(str(Path(top.stdout.strip()).resolve()))
            != os.path.normcase(str(project_root.resolve()))):
        return None  # a subdirectory of some other repo
    hooks_path = _git("config", "--get", "core.hooksPath")
    if hooks_path is not None and hooks_path.returncode == 0 and hooks_path.stdout.strip():
        logger.warning("[pre-commit] core.hooksPath is set (%s); scope gate not "
                       "installed -- call tools/check_scope.py --staged-only "
                       "from your hook manager", hooks_path.stdout.strip())
        return None
    git_dir = _git("rev-parse", "--git-dir")
    if git_dir is None or git_dir.returncode != 0:
        return None
    path = Path(git_dir.stdout.strip())
    if not path.is_absolute():
        path = project_root / path
    return path / "hooks"


def _install_commit_gates(project_root: Path) -> None:
    """Install / refresh the commit-time scope gate stubs (F9).

    One stub per COMMIT_GATES entry: pre-commit for ordinary commits and
    merge commits concluded by `git commit`, pre-merge-commit for automatic
    merge commits (which never run pre-commit). Each is written when absent
    or when the existing hook carries its marker; a foreign hook is never
    overwritten (doctor reports it). Always LF line endings -- a CRLF shell
    script fails to run.
    """
    hooks_dir = _git_hooks_dir(project_root)
    if hooks_dir is None:
        return
    for name, template, marker, command in COMMIT_GATES:
        hook = hooks_dir / name
        stub = template.read_text(encoding="utf-8")
        if hook.exists():
            current = hook.read_text(encoding="utf-8", errors="replace")
            if marker not in current:
                logger.warning("[%s] %s exists and is not governance-core's; "
                               "left unchanged -- add: %s", name, hook, command)
                continue
            if current.replace("\r\n", "\n") == stub:
                continue
        hooks_dir.mkdir(parents=True, exist_ok=True)
        with open(hook, "w", encoding="utf-8", newline="\n") as f:
            f.write(stub)
        os.chmod(hook, 0o755)
        logger.info("[%s] scope gate installed at %s", name, hook)


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
    # Issue #98: run hook subprocesses (and any harness-spawned Python) in
    # UTF-8 mode so stdin/stdout do not fall back to the OS locale (GBK/cp936
    # on Windows), which mis-decoded non-cp936 payloads and made gates fail
    # open. Defense-in-depth atop each hook's own UTF-8 byte read. Set
    # natively here so fresh installs ship the mitigation; merge-if-absent so
    # a consumer's existing env keys are never clobbered. (Art.4: membership
    # test, not a defaulted dict lookup.)
    env = data["env"] if "env" in data else {}
    if "PYTHONUTF8" not in env:
        env["PYTHONUTF8"] = "1"
    data["env"] = env
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    n = sum(len(g["hooks"]) for groups in governance_block.values() for g in groups)
    logger.info("[settings] wrote settings.local.json (%d governance hooks)", n)


def _pkg_source_path(rel_posix: str) -> Path | None:
    """Map an autonomy-layer relative path back to its package-source file.

    Used by the `upgrade --dry-run` drift diff (P-0073 Phase 2) to locate
    the incoming version of a locally-edited install-managed file. Returns
    None for a path that is not install-managed.
    """
    # Longest destination first: .claude/hooks/_gc_auth/ (vendored auth/)
    # lies inside .claude/hooks/.
    for src_sub, dst_sub in sorted(COPY_CATEGORIES,
                                   key=lambda c: len(c[1]), reverse=True):
        prefix = dst_sub + "/"
        if rel_posix.startswith(prefix):
            return PKG_ROOT / src_sub / rel_posix[len(prefix):]
    if rel_posix.startswith(CLAUSES_REL + "/"):
        return PKG_ROOT / "clauses" / rel_posix[len(CLAUSES_REL) + 1:]
    for src_sub, dst_sub in KNOWLEDGE_COPY_MAP:
        prefix = dst_sub + "/"
        if rel_posix.startswith(prefix):
            return PKG_ROOT / src_sub / rel_posix[len(prefix):]
    return None


def _drift_diffs(project_root: Path,
                 drifted: list[str]) -> list[tuple[str, str]]:
    """Return (rel_path, unified_diff) for each drifted file (P-0073 Phase 2).

    The diff is the consumer's current (personalized) content vs the
    incoming package-source version -- exactly what `upgrade` would
    overwrite, so the owner sees how their edit diverged from upstream.
    """
    diffs: list[tuple[str, str]] = []
    for rel in drifted:
        current = project_root / rel
        src = _pkg_source_path(rel)
        if src is None or not src.exists() or not current.exists():
            diffs.append((rel, "  (diff unavailable -- source not located)"))
            continue
        try:
            cur = current.read_text(encoding="utf-8").splitlines(keepends=True)
            new = src.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeDecodeError):
            diffs.append((rel, "  (diff unavailable -- unreadable file)"))
            continue
        diff = "".join(difflib.unified_diff(
            cur, new, fromfile=f"current/{rel}", tofile=f"incoming/{rel}"))
        diffs.append((rel, diff or "  (no textual difference)"))
    return diffs


def _local_additions(project_root: Path,
                     installed: list[tuple[Path, str]]) -> list[str]:
    """List autonomy-region files the owner added locally (P-0073 Phase 2).

    A file under a copy-category directory that is neither in the set the
    package would install nor in the previous manifest -- i.e. an
    owner-authored addition. The `.claude/skills/learned/` carve-out is
    excluded (learned skills are the candidate pipeline's domain). This
    list is the input for the Phase 3 semantic-conflict review.
    """
    install_paths = {p.relative_to(project_root).as_posix()
                     for p, _ in installed}
    old_paths: set[str] = set()
    manifest_path = project_root / INSTALLED_FILES_REL
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            old_paths = {e["path"] for e in old["files"]}
        except (json.JSONDecodeError, KeyError):
            pass
    additions: list[str] = []
    for _, dst_sub in COPY_CATEGORIES:
        region = project_root / dst_sub
        if not region.exists():
            continue
        for f in region.rglob("*"):
            if not f.is_file():
                continue
            if (f.suffix == ".pyc" or "__pycache__" in f.parts
                    or f.name.startswith(".")):
                continue  # bytecode / runtime state -- not an authored asset
            rel = f.relative_to(project_root).as_posix()
            if "/skills/learned/" in rel:
                continue
            if rel not in install_paths and rel not in old_paths:
                additions.append(rel)
    return sorted(additions)


def _dry_run_report(project_root: Path, installed: list[tuple[Path, str]],
                    drifted: list[str], pruned: list[str]) -> int:
    """Emit the `upgrade --dry-run` preview; write nothing. Returns 0.

    Reports the version delta (with a minor-skew note), the overwrite /
    drift / prune sets, a unified diff per drifted file, and the owner's
    local additions -- so an upgrade is reviewed, not applied blind.
    """
    from governance_core import __version__, version_util
    old_version = None
    manifest_path = project_root / INSTALLED_FILES_REL
    if manifest_path.exists():
        try:
            old_version = json.loads(manifest_path.read_text(
                encoding="utf-8"))["governance_core_version"]
        except (json.JSONDecodeError, KeyError):
            pass

    logger.info("[dry-run] governance-core upgrade preview "
                "-- nothing will be written")
    if old_version:
        logger.info("[dry-run] version: %s -> %s", old_version, __version__)
        gap = version_util.minor_gap(__version__, old_version)
        if gap >= 1:
            logger.info("[dry-run]   crosses %d minor version line(s) -- "
                        "review contracts/ for breaking changes before "
                        "upgrading", gap)
    logger.info("[dry-run] would overwrite %d install-managed file(s)",
                len(installed))
    if pruned:
        logger.info("[dry-run] would prune %d stale file(s): %s",
                    len(pruned), ", ".join(pruned))
    if drifted:
        logger.info("[dry-run] %d install-managed file(s) locally edited "
                    "(drift) -- would be captured as candidates, then "
                    "overwritten:", len(drifted))
        for rel, diff in _drift_diffs(project_root, drifted):
            logger.info("[dry-run] --- drift diff: %s ---", rel)
            for line in diff.rstrip("\n").splitlines():
                logger.info("  %s", line)
    additions = _local_additions(project_root, installed)
    if additions:
        logger.info("[dry-run] %d local addition(s) (not install-managed) "
                    "-- review for conflict with the incremental changes:",
                    len(additions))
        for rel in additions:
            logger.info("  + %s", rel)
    logger.info("[dry-run] no files written.")
    return 0


def install(
    project_root: Path,
    config_overrides: dict[str, Any] | None = None,
    preserve_config: bool = False,
    force: bool = False,
    auth_code: str | None = None,
    accept_candidate_uplink: bool = False,
    prune: bool = True,
    dry_run: bool = False,
    remove_config_auth_code: bool = False,
) -> int:
    """Install / upgrade the governance layer into `project_root`.

    P-0065 Phase 1: both an authorization gate and a candidate-uplink consent
    gate run BEFORE any autonomy-layer file is materialized. A failed gate
    returns non-zero and leaves the project without governance capabilities.
    Return codes: 1 missing root, 7 authorization failure, 8 consent denied.

    P-0070: `prune` (default True) removes autonomy-layer files dropped from
    the package source since the last install (manifest-diff). Pass False to
    keep stale files.

    P-0132: the code is stored in the gitignored `.governance/auth_code`,
    never in config.json. A pre-0.49 `authorization.auth_code` left in
    config.json is migrated to the file and kept until
    `remove_config_auth_code` -- clones of a multi-clone project still on an
    older version read it there.
    """
    project_root = project_root.resolve()
    if not project_root.exists():
        logger.error("[install] project root does not exist: %s", project_root)
        return 1

    config_overrides = config_overrides or {}
    cfg = _load_or_init_config(project_root, config_overrides, preserve_config)

    # --- P-0065 Phase 1: authorization + consent gate ----------------------
    # Both must pass before the autonomy layer (= governance capabilities) is
    # copied; gate first, materialize second.
    try:
        code, source = _resolve_auth_code(project_root, cfg, auth_code)
        previous = auth_store.read_code(project_root)
    except auth_store.AuthStoreError as exc:
        logger.error("[install] %s -- pass --auth-code <CODE> to rewrite it",
                     exc)
        return 7
    if not code:
        logger.error("[install] no authorization code. governance-core "
                      "requires a maintainer-issued code -- pass --auth-code "
                      "<CODE> (see README 'Authorization').")
        return 7
    try:
        payload = codec.verify_auth_code(code, codec.load_bundled_public_key())
    except codec.AuthCodeError as exc:
        logger.error("[install] authorization failed: %s", exc)
        return 7
    logger.info("[install] authorization code from %s", source)
    revoked = _install_time_revocation(code, payload)
    if revoked:
        logger.error("[install] authorization refused: %s -- contact the "
                     "governance-core maintainer", revoked)
        return 7
    if not _collect_consent(cfg, accept_candidate_uplink):
        logger.error("[install] candidate-uplink consent is REQUIRED in this "
                      "version -- install aborted. Re-run and consent, or "
                      "pass --accept-candidate-uplink.")
        return 8
    consumer_id = payload["consumer_id"]
    logger.info("[install] authorized: consumer_id=%r", consumer_id)

    # Preserve verified_at when the code is unchanged, so a repeated upgrade
    # does not churn a committed config.json (P-0065 Phase 2 dogfood finding).
    legacy = _legacy_config_code(cfg)
    unchanged = code == (previous if previous is not None else legacy)
    verified_at = _now_iso()
    if (unchanged and "authorization" in cfg
            and isinstance(cfg["authorization"], dict)
            and "verified_at" in cfg["authorization"]):
        verified_at = cfg["authorization"]["verified_at"]
    authorization: dict[str, Any] = {}
    if legacy is not None and not remove_config_auth_code:
        # Kept until --remove-config-auth-code: in a multi-clone project the
        # tracked config.json reaches clones still on < 0.49, whose
        # auth-guard reads the code from here (P-0132).
        authorization["auth_code"] = legacy
    elif legacy is not None:
        logger.info("[auth] removed authorization.auth_code from %s",
                    CONFIG_REL)
    authorization["consumer_id"] = consumer_id
    authorization["verified_at"] = verified_at
    cfg["authorization"] = authorization
    if not _consent_satisfied(cfg):
        cfg["candidate_uplink"] = {
            "consent": True,
            "consent_at": _now_iso(),
            "consent_terms_version": CONSENT_TERMS_VERSION,
        }
    if not dry_run:
        if previous != code:
            auth_store.write_code(project_root, code)
            logger.info("[auth] authorization code written to %s (gitignored)",
                        auth_store.AUTH_CODE_REL)
        _write_config(project_root, cfg)
    logger.info("[install] project=%s ritual_phrase=%r", cfg.get("project_name"), cfg.get("ritual_phrase"))

    # P-0065 Phase 4: capture locally-edited install-managed files as drift
    # candidates BEFORE the copy below overwrites them.
    drifted = _capture_drift(project_root, consumer_id, cfg, dry_run=dry_run)
    if drifted and not dry_run:
        sys.stderr.write(
            f"[drift] {len(drifted)} install-managed file(s) were locally "
            "edited; captured as drift candidates in the outbox "
            "(.governance/candidate-outbox/):\n"
            + "".join(f"  - {p}\n" for p in drifted))

    counts = {}
    # P-0065 Phase 2: collect every install-managed file written, for the
    # installed_files.json manifest.
    installed: list[tuple[Path, str]] = []
    for src_sub, dst_sub in COPY_CATEGORIES:
        src = PKG_ROOT / src_sub
        dst = project_root / dst_sub
        written = _copy_tree(src, dst, dry_run=dry_run)
        counts[f".claude/{src_sub}" if src_sub not in ("tools", "contracts", "agent_rules") else dst_sub] = len(written)
        installed.extend((p, CATEGORY_OF[src_sub]) for p in written)
    for src_sub, dst_sub in KNOWLEDGE_COPY_MAP:
        src = PKG_ROOT / src_sub
        dst = project_root / dst_sub
        # Only copy top-level files of the package subdir; skip recursive nesting
        # of methodology / operations (since they live under knowledge_governance/)
        n = 0
        if src.exists():
            for s in src.iterdir():
                if s.is_file() and s.name != "README.md":
                    d = dst / s.name
                    if not dry_run:
                        d.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(s, d)
                    installed.append((d, "knowledge"))
                    n += 1
        counts[dst_sub] = n

    clause_files, seeded_clauses = _render_clauses(project_root, cfg,
                                                   dry_run=dry_run)
    counts[".governance/clauses"] = len(clause_files)
    installed.extend((p, "clause") for p in clause_files)
    if seeded_clauses:
        counts[".governance/clauses (seeded, project-owned)"] = len(seeded_clauses)

    if not dry_run:
        _configure_gitattributes(project_root)
        _configure_gitignore(project_root)
        _ensure_boundary_anchor(project_root, cfg)
        _seed_state_md(project_root, cfg)
        _seed_constitution(project_root, cfg)
        _seed_allow_lists(project_root, cfg)
        _install_commit_gates(project_root)
        _write_settings_local_json(project_root)

    # P-0070: prune autonomy-layer files dropped from the package source,
    # BEFORE the manifest is rewritten (the diff needs the old manifest).
    pruned: list[str] = []
    if prune:
        pruned = _prune_stale(project_root, installed, dry_run=dry_run)
        if pruned and not dry_run:
            sys.stderr.write(
                f"[prune] {len(pruned)} stale install-managed file(s) "
                "removed (dropped from the package source):\n"
                + "".join(f"  - {p}\n" for p in pruned))

    # P-0073 Phase 2: dry-run stops here -- report the preview, write nothing.
    if dry_run:
        return _dry_run_report(project_root, installed, drifted, pruned)

    _write_installed_manifest(project_root, installed)

    logger.info("[install] complete. Files installed:")
    for k, v in counts.items():
        logger.info("  %-30s %d", k, v)

    return 0


def _report_auth_lifecycle(payload: dict[str, Any],
                           project_root: Path, code: str) -> None:
    """Log lease expiry + revocation-feed status (P-0071; informational).

    doctor does not fail on revocation -- the runtime auth-guard enforces
    it. This surfaces the lease countdown and the auth-guard feed cache so
    the maintainer/consumer can see how close to a freeze the project is.
    """
    if "expiry" in payload:
        try:
            days = (datetime.date.fromisoformat(str(payload["expiry"]))
                    - datetime.date.today()).days
            logger.info("[doctor] lease: expires %s (%d days left)",
                        payload["expiry"], days)
        except ValueError:
            logger.info("[doctor] lease: expiry %s", payload["expiry"])
    else:
        logger.info("[doctor] lease: no expiry in the code")

    if "revocation_feed_url" not in payload:
        return
    from governance_core.auth import revocation
    cache_path = revocation.feed_cache_path(project_root)
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - no cache -> auth-guard has not run
        logger.info("[doctor] revocation feed: not yet polled by auth-guard")
        return
    feed = cache.get("feed")
    if feed is None:
        logger.info("[doctor] revocation feed: no successful fetch yet "
                    "(first seen %s)", cache.get("first_seen"))
        return
    if revocation.is_revoked(feed, payload["consumer_id"]):
        status = "consumer REVOKED"
    elif revocation.is_revoked(feed, payload["consumer_id"],
                               codec.code_fingerprint(code)):
        status = "this code REVOKED (P-0132 per-code entry)"
    else:
        status = "not revoked"
    logger.info("[doctor] revocation feed: last fetch %s -- %s",
                cache.get("fetched_at"), status)


def _load_guard_common(project_root: Path):
    """Load the guards' _guard_common module the way the hooks see it.

    Prefers the installed copy (<project>/.claude/hooks/, what the guards
    actually execute); falls back to the package source copy.
    """
    import importlib.util
    for candidate in (project_root / CLAUDE_DIR / "hooks" / "_guard_common.py",
                      PKG_ROOT / "hooks" / "_guard_common.py"):
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location(
                "_gc_guard_common_doctor", candidate)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise FileNotFoundError("no _guard_common.py in .claude/hooks/ or package")


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
    # P-0129: this clone's agent identity must resolve from config -- the
    # guards fail closed (block every write) when it does not.
    guard_common = _load_guard_common(project_root)
    identity_err = guard_common.identity_failure(str(project_root))
    if identity_err:
        logger.error("[doctor] agent identity unresolved: %s -- this clone's "
                     "directory name must equal one agents[].clone_dir",
                     identity_err)
        return 10
    agent_name = guard_common.resolve_agent(str(project_root))
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
    # P-0081: runtime-import-discipline -- a shipped hook that imports
    # governance_core must guard it + fail open; a fail-closed gate must be
    # self-contained (else a broken package freezes every tool call). Any
    # unclassified importer fails doctor; auth-guard is a tracked exception
    # pending P-0082. See runtime_import_audit + the governance doc.
    from governance_core.runtime_import_audit import (
        check_runtime_import_discipline)
    disc = check_runtime_import_discipline(hooks_dir, set(_load_hooks_manifest()))
    if disc["violations"]:
        logger.error("[doctor] runtime-import-discipline: shipped hooks import "
                      "governance_core but are unclassified -- make them "
                      "self-contained or verify fail-open: %s",
                      disc["violations"])
        return 9
    if disc["exempt"]:
        logger.info("[doctor] runtime-import-discipline: %d tracked exception(s) "
                    "pending self-containment: %s",
                    len(disc["exempt"]), disc["exempt"])
    # P-0065 Phase 1: authorization must be present and still verify.
    # P-0132: the code lives in the gitignored .governance/auth_code.
    try:
        auth_code = auth_store.read_code(project_root)
    except auth_store.AuthStoreError as exc:
        logger.error("[doctor] %s (run install with --auth-code)", exc)
        return 7
    legacy_code = _legacy_config_code(cfg)
    if auth_code is None:
        if legacy_code is not None:
            logger.error("[doctor] authorization code not migrated to %s yet "
                         "-- run: governance-core upgrade",
                         auth_store.AUTH_CODE_REL)
        else:
            logger.error("[doctor] no authorization code at %s (run install "
                         "with --auth-code)", auth_store.AUTH_CODE_REL)
        return 7
    try:
        auth_payload = codec.verify_auth_code(
            auth_code, codec.load_bundled_public_key())
    except codec.AuthCodeError as exc:
        logger.error("[doctor] authorization invalid: %s", exc)
        return 7
    if legacy_code is not None:
        logger.warning("[doctor] authorization.auth_code is still stored in %s "
                       "(tracked by git: %s) -- once every clone runs >= 0.49.0: "
                       "governance-core upgrade --remove-config-auth-code",
                       CONFIG_REL,
                       "yes" if _git_tracks(project_root, CONFIG_REL) else "no")
    if _git_tracks(project_root, auth_store.AUTH_CODE_REL):
        logger.info("[doctor] note: %s is tracked by git (owner's choice) -- "
                    "keep this repository private", auth_store.AUTH_CODE_REL)
    # P-0065 Phase 1: candidate-uplink consent must be recorded
    if not _consent_satisfied(cfg):
        logger.error("[doctor] candidate-uplink consent not recorded for "
                      "current terms (required in this version)")
        return 8
    _report_auth_lifecycle(auth_payload, project_root, auth_code)
    # P-0129 F10: runtime files committed before the .gitignore block existed
    # stay tracked; informational (not an install defect).
    # P-0129 F3: a multi-clone clone without the boundary anchor confines its
    # session to the clone, so ../shared_state proposals are unwritable.
    if _boundary_anchor_wanted(project_root, cfg):
        anchor_path = project_root / CLAUDE_DIR / "settings.json"
        anchor_ok = False
        if anchor_path.exists():
            try:
                anchor = json.loads(anchor_path.read_text(encoding="utf-8"))
                anchor_ok = (isinstance(anchor, dict)
                             and BOUNDARY_ANCHOR_KEY in anchor)
            except (json.JSONDecodeError, OSError):
                anchor_ok = False
        if not anchor_ok:
            logger.warning("[doctor] multi-clone layout but %s has no %s -- "
                           "the session boundary stops at this clone; run "
                           "governance-core upgrade", anchor_path,
                           BOUNDARY_ANCHOR_KEY)
    # P-0129 F4: Claude Code loads only CLAUDE.md (generated from total.md);
    # a total.md that never points at a clause keeps the generic rules out of
    # the agent's context.
    total_md = project_root / "constitution" / "total.md"
    if (total_md.exists() and CLAUSES_REL + "/"
            not in total_md.read_text(encoding="utf-8")):
        logger.warning("[doctor] constitution/total.md references no %s/ file "
                       "-- the generic clauses never reach CLAUDE.md; add a "
                       "summary + pointer per clause via /iterate-constitution",
                       CLAUSES_REL)
    # P-0129 F9: commit-time scope gate + allow lists.
    empty_scopes = [a["name"] for a in cfg["agents"]
                    if a["name"] != cfg["core_agent_name"]
                    and _allow_rule_count(project_root, a["name"]) == 0]
    if empty_scopes:
        logger.warning("[doctor] agents with an empty allow list (can write "
                       "nothing outside .claude/ and shared_state/): %s -- "
                       "core fills agent_rules/<agent>.allow.txt",
                       empty_scopes)
    git_hooks_dir = _git_hooks_dir(project_root)
    if git_hooks_dir is not None:
        for name, _template, marker, command in COMMIT_GATES:
            hook = git_hooks_dir / name
            if not hook.exists():
                logger.warning("[doctor] no %s scope gate at %s -- run "
                               "governance-core upgrade", name, hook)
            elif marker not in hook.read_text(encoding="utf-8",
                                              errors="replace"):
                logger.warning("[doctor] %s is not governance-core's scope "
                               "gate; make sure it runs: %s", hook, command)
    tracked_runtime = _tracked_runtime_files(project_root)
    if tracked_runtime:
        logger.info("[doctor] note: runtime files still tracked by git (now "
                    "gitignored): %s -- untrack with: git rm --cached <path>",
                    tracked_runtime)
    # P-0097 (gc #85): repo-deletion root-cause check. Best-effort + ADVISORY:
    # loud-warn if the active gh token carries the delete_repo OAuth scope --
    # without which GitHub rejects every deletion regardless of how issued. Does
    # NOT change doctor's exit code (an auth-environment concern, not an install
    # defect; keeps dogfood/CI doctor exit-0 expectations).
    _scope_tool = PKG_ROOT / "tools" / "check_github_token_scope.py"
    if _scope_tool.exists():
        try:
            _sp = subprocess.run(
                [sys.executable, str(_scope_tool)],
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=30)
            _msg = ((_sp.stdout or "") + (_sp.stderr or "")).strip()
            if _sp.returncode == 1:
                logger.warning("[doctor] %s", _msg or "active gh token has "
                               "delete_repo scope -- repo deletion is POSSIBLE")
            elif _msg:
                logger.info("[doctor] %s", _msg)
        except (OSError, subprocess.SubprocessError) as _exc:
            logger.info("[doctor] token-scope check skipped: %s", _exc)
    logger.info("[doctor] OK: project=%s consumer_id=%r ritual_phrase=%r "
                "agent=%s agents=%d hooks=%d clauses=%d hooks_registered=%d",
                cfg["project_name"], cfg["authorization"]["consumer_id"],
                cfg["ritual_phrase"], agent_name, len(cfg["agents"]),
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
