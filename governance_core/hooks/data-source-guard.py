"""
Claude Code PreToolUse hook: data-source-guard.py

Independent hook (parallel to edit-write-guard.py on the PreToolUse chain)
that enforces the prepare_dataset.py single entry point for rules-agent
data ingestion. Per proposal `prepare_data_v2_single_entry_lockdown.md`
(Layer 1, 2026-04-29).

Blocks direct reads of long-lived dataset csv files unless the agent
routes through prepare_dataset's load_train_test_oos / load_oos_only
API. Mirrors edit-write-guard's L3/L5 transcript-grep model.

Trigger paths (Bash / Edit / Write target on any of these):
  artifacts/<pipeline>/data/event_samples*.csv
  artifacts/<pipeline>/data/full_features*.csv
  artifacts/<pipeline>/oos_validation/oos_base_data*.csv
  artifacts/<pipeline>/analysis/dense_predictions*.csv
  artifacts/<pipeline>/diagnostics/step9_*.csv
  artifacts/<pipeline>/datasets/{dense,oos,training}/**.csv

Detection:
  Bash: command string matches a read pattern
        (pd.read_csv / pl.read_csv / open) PLUS one of the data paths
  Edit/Write: target file_path matches one of the data paths

Exemptions:
  1. Cross-repo or write-target is prepare_dataset.py / dataset_registry.py
     itself (code edits, not data reads)
  2. Role is core or branch is master (governance authority — must be
     able to read any data for audit)
  3. Subagent context (transcript_path contains /subagents/) — parent's
     Agent invocation already passed governance
  4. Interactive REPL session marker in transcript (python -i / Jupyter
     kernel) — ad-hoc debug exemption per R7.3 (commit-time still gated
     by /prepare-data skill checks)
  5. Current turn transcript contains an authorized entry: a Skill call
     with skill="prepare-data" OR a tool_use whose input mentions
     `from <your-agent>.<your-pipeline>.prepare_dataset import` or `load_train_test_oos(`
     or `load_oos_only(` — i.e., the agent has explicitly committed to
     route through prepare_dataset

Exit codes: 0 allow, 2 block.
"""
import sys
import json
import os
import re
from pathlib import Path

_HOOK_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HOOK_DIR, "..", ".."))

sys.path.insert(0, _HOOK_DIR)
try:
    from _guard_common import (  # noqa: E402
        detect_role as _detect_role_shared,
        block as _block_shared,
    )
except ImportError as exc:
    sys.stderr.write(
        "\n[DATA-SOURCE GUARD FATAL] Cannot import _guard_common.py "
        f"(error: {exc}).\n"
        "Broken clone state. Run from agent-core: "
        "python tools/sync_infra.py --execute\n"
        "Blocking tool call until resolved.\n"
    )
    sys.exit(2)


def _detect_role() -> str:
    return _detect_role_shared(_REPO_ROOT)


def _block(reason: str, detail: str) -> None:
    _block_shared("DATA-SOURCE GUARD", reason, detail)


# ---------- Trigger path matchers ----------

_DATA_PATH_RES = [
    re.compile(r"artifacts/[^/\s'\"]+/data/event_samples[^/\s'\"]*\.csv"),
    re.compile(r"artifacts/[^/\s'\"]+/data/full_features[^/\s'\"]*\.csv"),
    re.compile(r"artifacts/[^/\s'\"]+/oos_validation/oos_base_data[^/\s'\"]*\.csv"),
    re.compile(r"artifacts/[^/\s'\"]+/analysis/dense_predictions[^/\s'\"]*\.csv"),
    re.compile(r"artifacts/[^/\s'\"]+/diagnostics/step9_[^/\s'\"]*\.csv"),
    re.compile(r"artifacts/[^/\s'\"]+/datasets/(?:dense|oos|training)/[^\s'\"]+\.csv"),
]

# Bash command must contain BOTH a read pattern AND a data path to fire
_BASH_READ_RE = re.compile(
    r"(?:pd|pandas|pl|polars)\.read_csv\(|(?<![A-Za-z_])open\(|read_csv\("
)

# Code-edit exemption: prepare_dataset.py / dataset_registry.py themselves
_CODE_EXEMPT_BASENAMES = ("prepare_dataset.py", "dataset_registry.py")


def _matches_data_path(text: str) -> str | None:
    """Return the first matching data path in text, or None."""
    for pat in _DATA_PATH_RES:
        m = pat.search(text)
        if m:
            return m.group(0)
    return None


# ---------- Authorized entry detection ----------

_AUTHORIZED_SKILL_NAMES = {"prepare-data"}

def _load_prep_entry_imports():
    """Project-specific prepare_dataset import prefixes from
    .governance/data_source_entries.json. Returns [] when the file is absent
    (the two generic function-call tokens below still apply)."""
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        cfg = repo_root / ".governance" / "data_source_entries.json"
        if not cfg.exists():
            return []
        data = json.loads(cfg.read_text(encoding="utf-8"))
        return [s for s in data.get("prep_entry_imports", []) if isinstance(s, str)]
    except Exception:
        return []


# Permissive substrings that indicate the agent committed to prepare_dataset.
# The import-path prefix is project-specific (config-injected via
# .governance/data_source_entries.json); the two function-call tokens are
# generic and always apply.
_PREP_ENTRY_TOKENS = tuple(_load_prep_entry_imports()) + (
    "load_train_test_oos(",
    "load_oos_only(",
)

# REPL-session markers — exempt for ad-hoc debugging (R7.3)
_REPL_MARKERS = (
    "python -i ",
    "ipython",
    "jupyter ",
    "ipykernel",
)


def _is_real_user_turn_boundary(entry: dict) -> bool:
    """True if entry marks a genuine user turn (not tool_result / skill body)."""
    if entry.get("type") != "user":
        return False
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


def _is_authorized_invocation(block: dict) -> bool:
    """True if this tool_use block is an authorized prepare_dataset entry."""
    if not isinstance(block, dict) or block.get("type") != "tool_use":
        return False
    name = block.get("name", "")
    inp = block.get("input", {}) or {}
    if name == "Skill" and inp.get("skill") in _AUTHORIZED_SKILL_NAMES:
        return True
    try:
        blob = json.dumps(inp)
    except Exception:
        return False
    if any(tok in blob for tok in _PREP_ENTRY_TOKENS):
        return True
    return False


def _has_repl_marker(block: dict) -> bool:
    """True if this tool_use input contains an interactive REPL marker."""
    if not isinstance(block, dict) or block.get("type") != "tool_use":
        return False
    inp = block.get("input", {}) or {}
    cmd = inp.get("command", "") or ""
    if not cmd:
        return False
    cmd_lc = cmd.lower()
    return any(mk in cmd_lc for mk in _REPL_MARKERS)


def _entry_allowed(data: dict) -> bool:
    """Scan transcript backwards from most recent entry to last real user
    turn boundary. Allow if any authorized prepare_dataset invocation OR
    REPL marker appears within that window.

    Subagent context bypasses the check (parent's Agent invocation already
    passed governance).

    Fail-closed: missing or unreadable transcript blocks.
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
            if _is_authorized_invocation(block):
                return True
            if _has_repl_marker(block):
                return True

    return False


# ---------- Main ----------

def _route_hint(matched_path: str) -> str:
    return (
        f"Reason: direct read of {matched_path} bypasses prepare_dataset "
        "single entry point (proposal Layer 1 R7).\n"
        "Route: from <your-agent>.<your-pipeline>.prepare_dataset import load_train_test_oos\n"
        "       prep = load_train_test_oos('<your-dataset-key>')\n"
        "       df = prep.train  # or .test / .oos\n"
        "Or invoke via Skill(skill=\"prepare-data\").\n"
        "Or, for ad-hoc REPL debugging, prefix the command with "
        "'python -i ' or run inside a Jupyter kernel."
    )


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    role = _detect_role()

    # Core / master-branch authority bypass — governance must be able to
    # audit data freely. Subagent transcripts also bypass via _entry_allowed.
    if role == "core":
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    matched_path: str | None = None

    if tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        if not cmd:
            sys.exit(0)
        if not _BASH_READ_RE.search(cmd):
            sys.exit(0)
        matched_path = _matches_data_path(cmd)
    elif tool_name in ("Edit", "Write"):
        file_path = tool_input.get("file_path", "") or ""
        if not file_path:
            sys.exit(0)
        # Code-edit exemption: editing prepare_dataset.py / dataset_registry.py
        # is not a data read — let edit-write-guard handle scope, we no-op.
        if os.path.basename(file_path) in _CODE_EXEMPT_BASENAMES:
            sys.exit(0)
        rel = file_path.replace("\\", "/")
        matched_path = _matches_data_path(rel)
    else:
        sys.exit(0)

    if not matched_path:
        sys.exit(0)

    if _entry_allowed(data):
        sys.exit(0)

    _block(
        f"{tool_name} BLOCKED (data-source-guard, role={role})",
        _route_hint(matched_path),
    )


if __name__ == "__main__":
    main()
