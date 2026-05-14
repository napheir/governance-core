# -*- coding: utf-8 -*-
"""
Claude Code UserPromptSubmit hook: prompt-context-router.py

Conditionally injects governance docs from knowledge/governance/ into the
agent's context when the user prompt contains a trigger keyword. Replaces
the old "everything in the constitution" pattern.

Config: knowledge/INDEX.routing.json

Hardening (R2/R10/R11 from harness audit):
  - Session-level dedup: a route already injected in this session is
    skipped (state in ~/.claude/cache/router_seen_<sessionid>.json)
  - max_total_lines_per_turn cap: prevents config error from injecting
    hundreds of lines per turn
  - Specific trigger phrases (not single tokens like 'P4') to reduce
    false-positive matches in unrelated discussion

Failure mode: silent no-op on any error. Hook is opportunistic
context, never critical path.
"""
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _detect_repo_root() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=3,
        )
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _load_routes(repo_root: str) -> dict:
    cfg = Path(repo_root) / "knowledge" / "INDEX.routing.json"
    if not cfg.is_file():
        return {}
    try:
        return json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _seen_path(session_id: str) -> Path:
    """Per-session dedup state. session_id from CC hook payload."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "default")[:64]
    return Path.home() / ".claude" / "cache" / f"router_seen_{safe}.json"


def _load_seen(session_id: str) -> set:
    p = _seen_path(session_id)
    if not p.is_file():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()


def _save_seen(session_id: str, seen: set) -> None:
    p = _seen_path(session_id)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    except OSError:
        pass


def _match_routes(prompt: str, routes: list, seen: set, dedup: bool) -> list:
    """Return matching routes (case-insensitive substring on triggers)."""
    p = prompt.lower()
    hits = []
    for route in routes:
        name = route.get("name", "")
        if dedup and name in seen:
            continue
        for t in route.get("triggers", []):
            if t.lower() in p:
                hits.append(route)
                break
    return hits


def _inject_route(repo_root: str, route: dict, line_budget: int) -> tuple:
    """Inject route's doc head; return (text, lines_used) or ('', 0)."""
    rel = route.get("path", "")
    if not rel:
        return "", 0
    fp = Path(repo_root) / rel
    if not fp.is_file():
        return "", 0
    try:
        content = fp.read_text(encoding="utf-8")
    except OSError:
        return "", 0
    requested = int(route.get("max_lines", 80))
    take = min(requested, line_budget)
    if take <= 0:
        return "", 0
    lines = content.splitlines()[:take]
    name = route.get("name", rel)
    text = (
        f"[Context Router] Injected {name} (path: {rel}, "
        f"first {len(lines)} lines):\n" + "\n".join(lines)
    )
    return text, len(lines)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt = data.get("prompt", "") or ""
    if not prompt.strip():
        sys.exit(0)

    repo_root = _detect_repo_root()
    if not repo_root:
        sys.exit(0)

    cfg = _load_routes(repo_root)
    if not isinstance(cfg, dict):
        sys.exit(0)
    routes = cfg.get("routes", [])
    if not routes:
        sys.exit(0)

    cap_per_turn = int(cfg.get("max_inject_per_turn", 1))
    cap_total_lines = int(cfg.get("max_total_lines_per_turn", 200))
    dedup = bool(cfg.get("session_dedup", True))

    session_id = data.get("session_id", "")
    seen = _load_seen(session_id) if dedup else set()

    candidates = _match_routes(prompt, routes, seen, dedup)[:cap_per_turn]
    if not candidates:
        sys.exit(0)

    out = []
    budget = cap_total_lines
    new_seen = set(seen)
    for route in candidates:
        if budget <= 0:
            break
        text, used = _inject_route(repo_root, route, budget)
        if text:
            out.append(text)
            budget -= used
            new_seen.add(route.get("name", ""))

    if dedup and new_seen != seen:
        _save_seen(session_id, new_seen)

    if out:
        sys.stdout.write("\n\n".join(out) + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
