"""Claude Code PreToolUse hook: proposal-classify-fast.py (P-0076 Phase 4).

Hard-block layer for Art.5.4 Proposal Classify Gate. Triggered on Edit / Write
/ MultiEdit / NotebookEdit; consults tools/proposal-classify-paths.json
(high-sensitivity allowlist). Behavior:

  target_path matches allowlist + session log has classify entry → allow
  target_path matches allowlist + session log has NO entry        → BLOCK (exit 2)
  target_path does not match                                       → allow (exit 0)

The hook is the missing 5th layer atop:
  L1 Art.5.4 governance clause
  L2 /proposal classify skill
  L3 proposal-vs-plan-mode-vs-commit guide
  L4 proposal-classify-reminder.py keyword soft reminder

Properties:
  - Fail-open: any exception → exit 0 + write to
    audit/proposal_classify_fast_errors.jsonl. Never locks the repo due to
    its own bug.
  - Escape hatch: env CLAUDE_CLASSIFY_FAST_DISABLE=1 → exit 0 immediately.
  - Wall-time: < 50ms in steady state (no subprocess; inline matcher).
"""
import json
import os
import sys
import traceback
from pathlib import Path
from datetime import datetime


_HOOK_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _HOOK_DIR.parent.parent

_PATHS_FILE = _REPO_ROOT / "tools" / "proposal-classify-paths.json"
_CLASSIFY_LOG = _REPO_ROOT / ".claude" / "cache" / "classify_log.jsonl"
_ERROR_LOG = _REPO_ROOT / "audit" / "proposal_classify_fast_errors.jsonl"

# Make tools/ importable for _classify_match
sys.path.insert(0, str(_REPO_ROOT / "tools"))


def _fail_open(reason: str, exc: Exception = None) -> int:
    try:
        _ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _ERROR_LOG.open("a", encoding="utf-8", newline="\n") as f:
            entry = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "reason": reason,
                "exc_type": type(exc).__name__ if exc else None,
                "exc_msg": str(exc) if exc else None,
                "tb": traceback.format_exc() if exc else None,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return 0


def _session_id() -> str:
    sid = os.environ.get("CLAUDE_SESSION_ID", "").strip()
    if sid:
        return sid
    fallback = Path.home() / ".claude" / "session_id_current.txt"
    if fallback.is_file():
        try:
            return fallback.read_text(encoding="utf-8").strip() or "unknown"
        except OSError:
            return "unknown"
    return "unknown"


def _extract_path(payload: dict) -> str:
    """Pull target path from Claude Code PreToolUse payload."""
    if not isinstance(payload, dict):
        return ""
    ti = payload.get("tool_input") or {}
    if isinstance(ti, dict):
        for key in ("file_path", "path", "notebook_path"):
            v = ti.get(key)
            if isinstance(v, str) and v:
                return v
    return ""


def _normalize(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    root_posix = str(_REPO_ROOT).replace("\\", "/") + "/"
    if p.startswith(root_posix):
        p = p[len(root_posix):]
    return p


def _load_paths() -> list:
    if not _PATHS_FILE.is_file():
        return []
    data = json.loads(_PATHS_FILE.read_text(encoding="utf-8"))
    return [(c, g) for c, body in data["categories"].items() for g in body["globs"]]


def _path_match(path_norm: str) -> tuple[str, str]:
    """Return (category, glob) on hit; ("", "") on miss."""
    from _classify_match import match
    for cat, glob in _load_paths():
        if match(path_norm, glob):
            return cat, glob
    return "", ""


def _session_has_classify_entry(session_id: str, path_norm: str) -> bool:
    """Has the current session classified this path (any verdict)?"""
    if not _CLASSIFY_LOG.is_file():
        return False
    try:
        for line in _CLASSIFY_LOG.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("session_id") != session_id:
                continue
            paths = entry.get("paths") or []
            if path_norm in paths:
                return True
    except OSError:
        return False
    return False


def main() -> int:
    if os.environ.get("CLAUDE_CLASSIFY_FAST_DISABLE", "").strip() == "1":
        return 0

    try:
        # Read stdin as UTF-8 bytes, not locale text mode: on a Windows
        # GBK/cp936 locale, sys.stdin.read() mis-decodes Chinese (or any
        # non-cp936) payloads and raises, routing a *valid* payload into the
        # fail-open branch below (issue #98: 313 logged "stdin parse failed"
        # fail-opens). UTF-8 byte decode is locale-independent.
        raw = sys.stdin.buffer.read().decode("utf-8")
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return _fail_open("stdin parse failed", e)

    try:
        path = _extract_path(payload)
        if not path:
            return 0

        path_norm = _normalize(path)
        cat, glob = _path_match(path_norm)
        if not cat:
            return 0

        sid = _session_id()
        if _session_has_classify_entry(sid, path_norm):
            sys.stderr.write(
                f"[proposal-classify-fast] OK -- path '{path_norm}' is in "
                f"'{cat}' allowlist, session has prior classify entry.\n"
            )
            return 0

        sys.stderr.write(
            f"\n[PROPOSAL CLASSIFY GATE BLOCK]\n"
            f"  Target:   {path_norm}\n"
            f"  Category: {cat}\n"
            f"  Glob:     {glob}\n"
            f"  Reason:   High-sensitivity path requires /proposal classify "
            f"before Edit/Write (Art.5.4).\n"
            f"\n"
            f"  Fix: run\n"
            f"    python tools/proposal_lib.py classify --path \"{path_norm}\" "
            f"--description \"<what you're about to change and why>\" --quick\n"
            f"\n"
            f"  This writes a classify log entry; retry the Edit afterwards.\n"
            f"  If verdict is PROPOSAL_REQUIRED, draft via /proposal create.\n"
            f"\n"
            f"  Escape hatch (rare; user-initiated): set env\n"
            f"    CLAUDE_CLASSIFY_FAST_DISABLE=1\n"
            f"  before starting the session (audited).\n"
        )
        return 2

    except Exception as e:
        return _fail_open("hook body raised", e)


if __name__ == "__main__":
    sys.exit(main())
