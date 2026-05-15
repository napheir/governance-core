"""
Claude Code PreToolUse hook: edit-write-guard.py

Intercepts Edit and Write tool calls with four layers of defense:
  1. Cross-repo blocking: files outside current repository are blocked
  2. Scope allowlist: files must match agent_rules/{role}.allow.txt
  3. knowledge/** entry-point enforcement: knowledge/** writes must be
     invoked via /learn skill or experiment-manager subagent (detected
     by transcript scan within the current user turn); direct Edit/Write
     bypasses the dashboard-rebuild hook wired into those entries
     (see commit 37eae77 + feedback_knowledge_writes_via_learn_skill).
  4. artifacts/<pipeline>/datasets/** registry enforcement: long-lived
     dataset writes must come after a DatasetRegistry().register/refresh/
     deprecate() call in the current turn (transcript scan), so every
     dataset gets vintage + lineage + supersedes-chain metadata. Required
     by proposal `dataset_registry_and_unified_artifacts_layout.md` §3.4.1.

Layer 2 is critical for bypassPermissions mode -- it ensures non-core
agents cannot modify files outside their declared scope, even when all
permission prompts are skipped.

Branch-based role detection (consistent with scope-guard.py):
  master / main       -> core   (governance authority, no restrictions)
  feature/trade-*     -> trade  (restricted by trade.allow.txt)
  feature/rules-*     -> rules  (restricted by rules.allow.txt)
  feature/data-*      -> data   (restricted by data.allow.txt)
  feature/research-*  -> research (restricted by research.allow.txt)
  unknown             -> core   (fail-open to most permissive)

Exit codes:
  0 = allow
  2 = block (Claude Code will not execute)
"""
import sys
import json
import os
import re
import time
import fnmatch

# Auto-detect repo root from hook location
_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HOOK_DIR, "..", ".."))

# Shared cross-cutting logic — same dir, add to sys.path before import.
# FAIL-CLOSED: if _guard_common is missing, exit 2 to block (otherwise
# import error → unspecified returncode → potential bypass).
sys.path.insert(0, _HOOK_DIR)
try:
    from _guard_common import (  # noqa: E402
        detect_role as _detect_role_shared,
        block as _block_shared,
    )
except ImportError as exc:
    sys.stderr.write(
        "\n[EDIT-WRITE GUARD FATAL] Cannot import _guard_common.py "
        f"(error: {exc}).\n"
        "Broken clone state. Run from agent-core: "
        "python tools/sync_infra.py --execute\n"
        "Blocking tool call until resolved.\n"
    )
    sys.exit(2)

# Shared runtime state directory (<install-root>/shared_state) lives outside
# any clone's git worktree. All agents may read/write here — see CLAUDE.md
# 第四条之一. This path must be whitelisted before the cross-repo check.
_SHARED_STATE_ROOT = os.path.normpath(os.path.join(_REPO_ROOT, "..", "shared_state"))

# Cache for allow rules (loaded once per hook invocation)
_allow_cache = {}


def _detect_role() -> str:
    """Detect agent role from current git branch (delegates to shared)."""
    return _detect_role_shared(_REPO_ROOT)


def _load_allow_rules(role: str) -> list:
    """Load allow rules from agent_rules/{role}.allow.txt.

    Returns list of path prefixes/patterns the role may modify.
    Falls back to empty list if file not found (deny all).
    """
    if role in _allow_cache:
        return _allow_cache[role]

    allow_file = os.path.join(_REPO_ROOT, "agent_rules", f"{role}.allow.txt")
    rules = []
    try:
        with open(allow_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Strip trailing /** for prefix matching
                    rules.append(line)
    except FileNotFoundError:
        pass
    except Exception:
        pass

    _allow_cache[role] = rules
    return rules


def _load_deny_rules() -> list:
    """Load shared deny rules from agent_rules/shared.deny.txt."""
    deny_file = os.path.join(_REPO_ROOT, "agent_rules", "shared.deny.txt")
    rules = []
    try:
        with open(deny_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    rules.append(line)
    except FileNotFoundError:
        pass
    return rules


def _is_path_allowed(rel_path: str, role: str) -> bool:
    """Check if relative path is allowed by role's allow rules.

    Matching logic (consistent with tools/check_scope.py):
    - 'trade/**' matches 'trade/foo.py', 'trade/sub/bar.py'
    - 'config/trade_config.json' matches exact file
    - 'proposals/' matches 'proposals/anything'
    - 'STATE.md' matches exact file
    """
    allow_rules = _load_allow_rules(role)
    deny_rules = _load_deny_rules()

    # Normalize path separators
    rel_path = rel_path.replace("\\", "/")

    # Check deny rules first (shared.deny.txt)
    for deny in deny_rules:
        deny_norm = deny.rstrip("/").replace("\\", "/")
        if rel_path == deny_norm or rel_path.startswith(deny_norm + "/"):
            return False

    # Check allow rules
    for rule in allow_rules:
        rule_norm = rule.replace("\\", "/")

        # Pattern with /** glob: 'trade/**' -> matches 'trade/anything'
        if rule_norm.endswith("/**"):
            prefix = rule_norm[:-3]  # Remove '/**'
            if rel_path == prefix or rel_path.startswith(prefix + "/"):
                return True

        # Directory pattern with trailing /: 'data/' -> matches 'data/anything'
        elif rule_norm.endswith("/"):
            if rel_path.startswith(rule_norm) or rel_path == rule_norm.rstrip("/"):
                return True

        # Exact file match: 'config/trade_config.json'
        elif rel_path == rule_norm:
            return True

        # Directory without trailing / or glob: 'proposals' -> matches 'proposals/anything'
        elif not os.path.splitext(rule_norm)[1]:
            # No extension = likely a directory
            if rel_path == rule_norm or rel_path.startswith(rule_norm + "/"):
                return True

    return False


def _log_hook_decision(data: dict, rel_path: str, role: str, decision: str, layer: str) -> None:
    """Append JSON line to ~/.claude/hook-payload-debug.log per knowledge/** or
    datasets/** Edit/Write decision.

    Per rules-agent 2026-04-27 bug report: Layer 3 inconsistently blocked
    knowledge/datasets/ writes while allowing knowledge/decisions/ and
    knowledge/models/ in the SAME experiment-manager subagent turn.
    Hypothesis: harness sends different transcript_path values across these
    calls (e.g., subagent's own transcript for some, parent's for others, or
    empty/missing for some). This log captures the input payload + decision
    every time the guard fires on a knowledge/** or datasets/** path so we
    can post-hoc correlate divergent transcript_path against the same-turn
    decision split. Failure-tolerant: logging never blocks the hook.
    """
    log_path = os.path.expanduser("~/.claude/hook-payload-debug.log")
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        transcript_path = data.get("transcript_path", "")
        tp_norm = transcript_path.replace("\\", "/") if transcript_path else ""
        entry = {
            "ts": time.time(),
            "pid": os.getpid(),
            "tool": data.get("tool_name", ""),
            "role": role,
            "rel_path": rel_path,
            "decision": decision,
            "layer": layer,
            "transcript_path": transcript_path,
            "transcript_has_subagents_marker": "/subagents/" in tp_norm,
            "transcript_file_exists": bool(transcript_path and os.path.isfile(transcript_path)),
            "session_id": data.get("session_id", ""),
            "hook_event_name": data.get("hook_event_name", ""),
            # Capture full payload keys (not values; values may be huge) so we
            # can spot if some calls are missing keys others have.
            "payload_keys": sorted(list(data.keys())),
        }
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # never break the hook on logging failure


def _block(reason: str, detail: str) -> None:
    """Print block message and exit with code 2 (delegates to shared)."""
    _block_shared("SCOPE GUARD", reason, detail)


# ---------- Layer 3: knowledge/** entry-point enforcement ----------

_AUTHORIZED_SKILL_NAMES = {"learn"}
_AUTHORIZED_SUBAGENT_TYPES = {"experiment-manager"}


def _is_real_user_turn_boundary(entry: dict) -> bool:
    """True if entry marks a genuine user turn (not a tool_result reply
    nor a slash-command/skill body injection).

    CC transcripts encode several things as type=user entries:
      1. Real user-typed messages (boundary)
      2. tool_result replies to the assistant's tool_use (NOT a boundary)
      3. Slash-command / Skill body injections — the skill's prompt body
         is fed back to the model wrapped as type=user with isMeta=True
         and sourceToolUseID pointing at the originating Skill tool_use
         (NOT a boundary; this is a continuation of the assistant turn)

    Without the meta-injection check, walk-back from a knowledge/** or
    datasets/** Edit/Write breaks at the skill body injection BEFORE
    reaching the Skill tool_use that authorized the write — manifesting
    as spurious 'BLOCKED (entry-point)' errors when the agent is in fact
    inside an authorized /learn or experiment-manager invocation.
    """
    if entry.get("type") != "user":
        return False
    # Skill / slash-command body injections look like fresh user messages
    # (type=user, content=list[text]) but are tagged isMeta=True and carry
    # sourceToolUseID linking back to the originating tool_use. Skip them.
    if entry.get("isMeta") is True or entry.get("sourceToolUseID"):
        return False
    content = entry.get("message", {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                return False
        return True
    return False


def _is_authorized_entry_invocation(block: dict) -> bool:
    """True if this tool_use block is an authorized knowledge/ entry point."""
    if not isinstance(block, dict) or block.get("type") != "tool_use":
        return False
    name = block.get("name", "")
    inp = block.get("input", {}) or {}
    if name == "Skill" and inp.get("skill") in _AUTHORIZED_SKILL_NAMES:
        return True
    if name == "Agent" and inp.get("subagent_type") in _AUTHORIZED_SUBAGENT_TYPES:
        return True
    return False


def _knowledge_entry_allowed(data: dict) -> bool:
    """Layer 3 gate: knowledge/** writes must come from an authorized entry.

    Detection: scan transcript backwards from the most recent entry until
    the last real user turn boundary. Allow if any Skill({learn}) or
    Agent({experiment-manager}) tool_use appears within that window.

    Subagent context (transcript_path contains '/subagents/') is allowed
    unconditionally -- subagents run under their parent's governance, and
    the parent's Agent invocation (which granted the subagent authority)
    already passed through this guard.

    Fail-closed: if transcript_path is missing or unreadable, block --
    the agent must explicitly route via /learn or experiment-manager.
    """
    transcript_path = data.get("transcript_path", "")

    # Subagent context is allowed (V1: trust parent's invocation decision)
    if transcript_path and "/subagents/" in transcript_path.replace("\\", "/"):
        return True

    if not transcript_path or not os.path.isfile(transcript_path):
        return False

    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return False

    # Walk backwards from most recent; stop at last real user turn boundary
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if _is_real_user_turn_boundary(entry):
            break

        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if _is_authorized_entry_invocation(block):
                return True

    return False


# ---------- Layer 6: destructive content scan ----------
#
# Per proposal harden_indirect_attack_paths.md Phase B. Hybrid mode:
# BLOCK_PATTERNS always block (literal critical destruction patterns);
# WARN_PATTERNS warn-and-pass (variable/parameterized forms with FP risk).
#
# Mode override via agent_rules/destructive_content_mode.txt:
#   absent or empty -> hybrid (default; Q2 user choice)
#   "block"          -> escalate WARN to also block
#   "off"            -> skip Layer 6 entirely (escape hatch)
#
# All warns + blocks are appended to <repo>/audit/destructive_content_alerts.jsonl.

_DESTRUCTIVE_SCAN_EXTS = {
    ".py", ".ps1", ".psm1", ".psd1",
    ".sh", ".bash", ".zsh",
    ".bat", ".cmd",
}

# Critical literal-target destruction. NEVER legit in agent-authored
# scripts. Always block regardless of mode.
_DESTRUCTIVE_BLOCK_PATTERNS = [
    # shutil.rmtree('.git') / rmtree('/') / rmtree('~') literal targets
    (re.compile(r"\bshutil\.rmtree\s*\(\s*['\"](?:[A-Za-z]:[/\\])?[/\\]?\.git\b"),
     "shutil.rmtree on .git literal"),
    (re.compile(r"\bshutil\.rmtree\s*\(\s*['\"]/['\"]"),
     "shutil.rmtree on / literal"),
    (re.compile(r"\bshutil\.rmtree\s*\(\s*['\"]~['\"]"),
     "shutil.rmtree on ~ literal"),
    # os.unlink on .git/refs/HEAD etc
    (re.compile(r"\bos\.unlink\s*\(\s*['\"][^'\"]*\.git/[^'\"]+['\"]"),
     "os.unlink on .git/* literal"),
    # subprocess running 'rm -rf /' or 'rm -rf .git' as literal arg list
    (re.compile(r"\bsubprocess\.\w+\s*\([^)]*['\"]rm\s+-rf\s+[/.]"),
     "subprocess rm -rf literal critical"),
    # PowerShell Remove-Item with literal .git target
    (re.compile(r"Remove-Item\b[^)\n]*?-(?:Recurse|Force)[^)\n]*?['\"](?:[A-Za-z]:[/\\])?[/\\]?\.git\b"),
     "Remove-Item on .git literal"),
]

# Variable/parameterized destructive patterns. Default WARN (FP risk:
# unit tests legit do shutil.rmtree(tmpdir); business code legit calls
# subprocess.run(['rm', '-rf', '/tmp/build'])). Mode='block' escalates.
_DESTRUCTIVE_WARN_PATTERNS = [
    (re.compile(r"\bshutil\.rmtree\s*\("), "shutil.rmtree (variable arg)"),
    (re.compile(r"\bos\.removedirs\s*\("), "os.removedirs"),
    (re.compile(r"\bos\.unlink\s*\("), "os.unlink (variable arg)"),
    (re.compile(r"\bRemove-Item\s+(?:-\w+\s+)*(-Recurse|-Force)"),
     "Remove-Item with destructive flags"),
    (re.compile(r"\bsubprocess\.\w+\s*\([^)]*['\"](?:rm|del|Remove-Item)\b"),
     "subprocess invoking destructive cmd"),
    (re.compile(r"(?i)\b(drop|truncate)\s+(table|database|schema)\b"),
     "SQL DDL drop in script content"),
    (re.compile(r"\bgit\s+push\s+(?:-f\b|--force)"), "git force-push in script"),
    (re.compile(r"\bgit\s+filter-branch\b"), "git filter-branch in script"),
    (re.compile(r"\bgit\s+reflog\s+expire\s+--expire=now"),
     "git reflog expire-all in script"),
]


def _destructive_content_mode() -> str:
    """Read agent_rules/destructive_content_mode.txt; return 'hybrid' (default), 'block', or 'off'."""
    mode_file = os.path.join(_REPO_ROOT, "agent_rules", "destructive_content_mode.txt")
    try:
        with open(mode_file, encoding="utf-8") as f:
            content = f.read().strip().lower()
        if content in ("block", "off"):
            return content
    except (FileNotFoundError, OSError):
        pass
    return "hybrid"


def _destructive_audit(rel_path: str, role: str, hits: list, level: str) -> None:
    """Append one JSON line to <repo>/audit/destructive_content_alerts.jsonl."""
    audit_dir = os.path.join(_REPO_ROOT, "audit")
    try:
        os.makedirs(audit_dir, exist_ok=True)
    except OSError:
        return
    record = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "rel_path": rel_path,
        "role": role,
        "level": level,
        "hits": hits,
    }
    try:
        with open(os.path.join(audit_dir, "destructive_content_alerts.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _destructive_content_check(rel_path: str, content: str, role: str) -> None:
    """Layer 6: scan Write/Edit content for destructive patterns. Block /
    warn / pass according to hybrid mode + match category. Always exits
    via _block() if any BLOCK pattern matches OR if mode='block' and any
    WARN matches.
    """
    if not content:
        return

    ext = os.path.splitext(rel_path)[1].lower()
    if ext not in _DESTRUCTIVE_SCAN_EXTS:
        return

    mode = _destructive_content_mode()
    if mode == "off":
        return

    # Phase 1: BLOCK list (always blocks regardless of mode)
    block_hits = []
    for pat, label in _DESTRUCTIVE_BLOCK_PATTERNS:
        if pat.search(content):
            block_hits.append(label)
    if block_hits:
        _destructive_audit(rel_path, role, block_hits, level="block")
        _block(
            f"Edit/Write BLOCKED (destructive content, role={role})",
            f"Target: {rel_path}\n"
            f"Role:   {role}\n\n"
            "Content contains LITERAL critical destruction patterns:\n"
            + "\n".join(f"  - {h}" for h in block_hits) + "\n\n"
            "These are never legitimate in agent-authored code (literal\n"
            ".git / / / ~ targets). If this is a unit test or governance\n"
            "tool that genuinely needs this pattern, route via /learn or\n"
            "experiment-manager (which the L3 entry-point check exempts).\n\n"
            "If you believe this is a false positive, set\n"
            "agent_rules/destructive_content_mode.txt to 'off' (escape\n"
            "hatch) and retry."
        )

    # Phase 2: WARN list -- mode-dependent action
    warn_hits = []
    for pat, label in _DESTRUCTIVE_WARN_PATTERNS:
        if pat.search(content):
            warn_hits.append(label)
    if warn_hits:
        if mode == "block":
            _destructive_audit(rel_path, role, warn_hits, level="block-escalated")
            _block(
                f"Edit/Write BLOCKED (destructive content, mode=block, role={role})",
                f"Target: {rel_path}\n"
                f"Role:   {role}\n\n"
                "Content contains destructive patterns (mode=block escalates "
                "WARN to BLOCK):\n"
                + "\n".join(f"  - {h}" for h in warn_hits) + "\n\n"
                "Switch to mode=hybrid (default) if these are legitimate."
            )
        else:
            # hybrid mode: warn + audit, allow
            _destructive_audit(rel_path, role, warn_hits, level="warn")
            sys.stderr.write(
                f"\n[DESTRUCTIVE CONTENT WARN] role={role} target={rel_path}\n"
                + "\n".join(f"  - {h}" for h in warn_hits) + "\n"
                "  (allowed; audited at audit/destructive_content_alerts.jsonl)\n\n"
            )


# ---------- Layer 4: artifacts/<pipeline>/datasets/** registry enforcement ----------

# Match paths like 'artifacts/<your-pipeline>/datasets/dense/foo.csv' (any pipeline)
_DATASETS_PATH_RE = re.compile(r"^artifacts/[^/]+/datasets/")

# Match a registry method call in serialized tool_use input. Detection is
# permissive: the blob must contain both `DatasetRegistry` (any reference
# -- direct chain `DatasetRegistry("p").register(` OR variable-bound
# `reg = DatasetRegistry("p"); reg.register(`) AND a method-call pattern
# `.register(`/`.refresh(`/`.deprecate(`. False-positive risk (unrelated
# class with same method name) is accepted: this hook is guidance, not
# a hard security boundary -- the registry's own validate() catches malformed
# entries downstream.
_REGISTRY_METHOD_RE = re.compile(r"\.(register|refresh|deprecate)\(", re.DOTALL)


# ---------- Layer 5: constitution/** + CLAUDE.md entry-point enforcement ----------

_CONSTITUTION_PATHS = {
    "constitution/total.md",
    "constitution/agent.md",
    "CLAUDE.md",
}
_AUTHORIZED_CONSTITUTION_SKILL = "iterate-constitution"


def _constitution_entry_allowed(data: dict) -> bool:
    """Layer 5 gate: constitution source files require iterate-constitution skill.

    Mirrors L3 (knowledge entry-point) pattern. Edits to constitution/total.md,
    constitution/agent.md, or CLAUDE.md must be invoked from a transcript
    where the most recent user turn contains a tool_use of:
      Skill(skill="iterate-constitution")

    This funnels all constitution amendments through the skill's decision
    tree (total vs agent vs ADR vs skill placement) + automatic regen +
    audit + sync orchestration. See proposals/iterate_constitution_skill.md.

    Subagent context (transcript_path contains '/subagents/') is allowed
    unconditionally — the parent's Agent invocation already passed L5.

    Fail-closed: missing or unreadable transcript blocks the edit.
    """
    transcript_path = data.get("transcript_path", "")

    if transcript_path and "/subagents/" in transcript_path.replace("\\", "/"):
        return True

    if not transcript_path or not os.path.isfile(transcript_path):
        return False

    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return False

    # Walk backwards to last real user turn boundary; reuse L3 helpers.
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if _is_real_user_turn_boundary(entry):
            break

        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") == "Skill":
                inp = block.get("input", {}) or {}
                if inp.get("skill") == _AUTHORIZED_CONSTITUTION_SKILL:
                    return True

    return False


def _datasets_entry_allowed(rel_path: str, data: dict) -> bool:
    """Layer 4 gate: datasets/** writes must follow a DatasetRegistry call.

    Exemption: registry.jsonl itself is the registry's own append target;
    writing it is the registration act, not a candidate for enforcement.

    Detection: identical scheme to Layer 3 -- scan transcript backwards
    from most recent entry until the last real user turn boundary; any
    tool_use whose serialized input contains DatasetRegistry().{register,
    refresh,deprecate}( unlocks subsequent dataset writes for this turn.
    """
    if rel_path.endswith("/registry.jsonl") or rel_path == "registry.jsonl":
        return True

    transcript_path = data.get("transcript_path", "")
    if transcript_path and "/subagents/" in transcript_path.replace("\\", "/"):
        return True
    if not transcript_path or not os.path.isfile(transcript_path):
        return False

    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return False

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue

        if _is_real_user_turn_boundary(entry):
            break

        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            inp = block.get("input", {}) or {}
            try:
                blob = json.dumps(inp)
            except Exception:
                continue
            if "DatasetRegistry" in blob and _REGISTRY_METHOD_RE.search(blob):
                return True

    return False


def main() -> None:
    """Block Edit/Write operations outside agent's declared scope."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    role = _detect_role()

    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    # Layer 5 must check BEFORE the core early-exit — the
    # iterate-constitution skill is mandatory for ALL roles (R5 audit
    # 2026-04-28 proved core also makes "wrong-file" mistakes).
    # Subagent transcripts ("/subagents/" path) and
    # ~/.claude/ paths still bypass via _constitution_entry_allowed().
    target = os.path.normpath(os.path.abspath(file_path))
    repo = os.path.normpath(_REPO_ROOT)
    _user_claude_dir = os.path.normpath(
        os.path.join(os.path.expanduser("~"), ".claude")
    )
    if not target.startswith(_user_claude_dir + os.sep):
        rel_path_for_l5 = os.path.relpath(target, repo).replace("\\", "/")
        if rel_path_for_l5 in _CONSTITUTION_PATHS:
            allowed_l5 = _constitution_entry_allowed(data)
            _log_hook_decision(
                data, rel_path_for_l5, role,
                decision="allow" if allowed_l5 else "block",
                layer="L5-constitution-entry-point",
            )
            if not allowed_l5:
                _block(
                    f"Edit/Write BLOCKED (constitution entry-point, role={role})",
                    f"Target: {rel_path_for_l5}\n\n"
                    "Constitution amendments must route through the\n"
                    "/iterate-constitution skill so the decision tree\n"
                    "(total vs agent vs ADR vs skill), regen + audit + sync\n"
                    "steps all run automatically.\n\n"
                    "Route:\n"
                    "  Skill(skill=\"iterate-constitution\", ...)\n\n"
                    "Then retry the Edit. Detection: transcript scan back\n"
                    "to the last real user turn boundary.\n\n"
                    "CLAUDE.md is a generated artifact — DO NOT edit\n"
                    "directly. All changes go to constitution/total.md or\n"
                    "constitution/agent.md sources; pre-commit auto-regens.\n"
                )

    # Layer 6: destructive content scan (proposal harden_indirect_attack_paths
    # Phase B). Applies to ALL roles (including core) -- "I'm core" is not
    # an authorization signal for shutil.rmtree('.git') etc. Hybrid mode:
    # literal critical patterns block; variable forms warn + audit.
    rel_path_for_l6 = os.path.relpath(target, repo).replace("\\", "/")
    _content_to_scan = ""
    if data.get("tool_name") == "Write":
        _content_to_scan = tool_input.get("content", "")
    elif data.get("tool_name") == "Edit":
        _content_to_scan = tool_input.get("new_string", "")
        for edit in tool_input.get("edits", []) or []:
            if isinstance(edit, dict):
                _content_to_scan += "\n" + edit.get("new_string", "")
    if _content_to_scan:
        _destructive_content_check(rel_path_for_l6, _content_to_scan, role)

    # Core agent has governance authority over all scopes (L1-L4 bypass)
    if role == "core":
        sys.exit(0)

    # Normalize paths
    target = os.path.normpath(os.path.abspath(file_path))
    repo = os.path.normpath(_REPO_ROOT)

    # Allow Claude Code internal working files (~/.claude/)
    _user_claude_dir = os.path.normpath(
        os.path.join(os.path.expanduser("~"), ".claude")
    )
    if target.startswith(_user_claude_dir + os.sep):
        sys.exit(0)

    # Allow shared runtime state (<install-root>/shared_state/) — multi-clone
    # writable by design. Per CLAUDE.md 第四条之一, writers must use filelock
    # + atomic replace; the guard only governs path authorization.
    if target == _SHARED_STATE_ROOT or target.startswith(_SHARED_STATE_ROOT + os.sep):
        sys.exit(0)

    # Layer 1: Cross-repo blocking
    if not target.startswith(repo + os.sep) and target != repo:
        repo_name = os.path.basename(repo)
        _block(
            f"Edit/Write BLOCKED (cross-repo, role={role})",
            f"Target: {file_path}\n"
            f"Repo:   {repo_name}/\n"
            f"Role:   {role} (only core can modify cross-repo files)\n"
            "Create a proposal in proposals/ for cross-repo changes."
        )

    # Layer 2: Scope allowlist (within repo)
    rel_path = os.path.relpath(target, repo).replace("\\", "/")

    # .claude/ directory is always writable by the agent working in this repo
    if rel_path.startswith(".claude/") or rel_path == ".claude":
        sys.exit(0)

    if not _is_path_allowed(rel_path, role):
        _block(
            f"Edit/Write BLOCKED (scope violation, role={role})",
            f"Target: {rel_path}\n"
            f"Role:   {role}\n"
            f"This file is not in your allow list (agent_rules/{role}.allow.txt).\n"
            "Create a proposal in proposals/ to request access."
        )

    # Layer 3: knowledge/** entry-point enforcement (non-core agents)
    if rel_path == "knowledge" or rel_path.startswith("knowledge/"):
        allowed_l3 = _knowledge_entry_allowed(data)
        _log_hook_decision(
            data, rel_path, role,
            decision="allow" if allowed_l3 else "block",
            layer="L3-knowledge-entry-point",
        )
        if not allowed_l3:
            _block(
                f"Edit/Write BLOCKED (knowledge/** entry-point, role={role})",
                f"Target: {rel_path}\n"
                f"Role:   {role}\n\n"
                "knowledge/** writes must be invoked via an authorized entry,\n"
                "otherwise the dashboard-rebuild hook is bypassed and the\n"
                "rendered view drifts from the committed archive state\n"
                "(see commits 37eae77 + feedback_knowledge_writes_via_learn_skill).\n\n"
                "Route one of:\n"
                "  - New experiment archive:\n"
                "      Agent(subagent_type=\"experiment-manager\", ...)\n"
                "  - Any other knowledge/** file:\n"
                "      Skill(skill=\"learn\", ...)\n\n"
                "Detection scope: transcript scan back to the last real\n"
                "user turn boundary. Once an authorized invocation appears\n"
                "in the current turn, subsequent Edit/Write to knowledge/**\n"
                "in the same turn are allowed.\n"
            )

    # Layer 5 was checked above (before core early-exit) for constitution
    # source files — applies to all roles including core. See top of main().

    # Layer 4: artifacts/<pipeline>/datasets/** registry enforcement
    if _DATASETS_PATH_RE.match(rel_path):
        allowed_l4 = _datasets_entry_allowed(rel_path, data)
        _log_hook_decision(
            data, rel_path, role,
            decision="allow" if allowed_l4 else "block",
            layer="L4-datasets-registry",
        )
        if not allowed_l4:
            _block(
                f"Edit/Write BLOCKED (datasets/** entry-point, role={role})",
                f"Target: {rel_path}\n"
                f"Role:   {role}\n\n"
                "Long-lived dataset writes must be authorized via DatasetRegistry,\n"
                "otherwise the new file lacks vintage + lineage + supersedes\n"
                "metadata and the next architecture upgrade will hit the same\n"
                "'pre-O2 dense vs O2 dense' confusion (proposal\n"
                "dataset_registry_and_unified_artifacts_layout.md §1.1).\n\n"
                "Route:\n"
                "  from <your-agent>.<your-pipeline>.dataset_registry import DatasetRegistry\n"
                "  reg = DatasetRegistry(\"strangle50\")\n"
                "  reg.register({...})           # new dataset\n"
                "  reg.refresh(dataset_id, ...)  # same kind+arch, new vintage\n"
                "  reg.deprecate(old_id, replaced_by=new_id, reason=...)\n\n"
                "Detection scope: transcript scan back to the last real\n"
                "user turn boundary. Exemption: registry.jsonl itself is the\n"
                "registration target and is always allowed.\n"
            )

    sys.exit(0)


if __name__ == "__main__":
    main()
