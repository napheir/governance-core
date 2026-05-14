# -*- coding: utf-8 -*-
"""
Claude Code UserPromptSubmit hook: proposal-classify-reminder.py

Soft reminder: when user prompt contains keywords indicating non-trivial
work (redesign / migrate / schema / 重构 / etc), inject a context note
pointing to Art.5.4 and the /proposal classify gate. Never blocks; always
exits 0; emits empty stdout when no keyword matches.

Config: ~/.claude/hooks/proposal-classify-keywords.json (hot-editable;
empty/missing list = effectively disabled).

Per proposal P-0058 (classify gate enforcement, Phase 1).
"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

CONFIG_PATH = Path.home() / ".claude" / "hooks" / "proposal-classify-keywords.json"


def _load_keywords() -> list:
    if not CONFIG_PATH.is_file():
        return []
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return [str(k) for k in data.get("keywords", []) if isinstance(k, str)]
    except (OSError, json.JSONDecodeError):
        pass
    return []


def _extract_prompt(stdin_data) -> str:
    """Pull user prompt text from Claude Code hook payload.

    Schema varies across harness versions; try common field names and
    fall back to empty string (silent no-op on shape mismatch).
    """
    if not isinstance(stdin_data, dict):
        return ""
    for key in ("prompt", "user_message", "user_prompt", "message"):
        val = stdin_data.get(key)
        if isinstance(val, str):
            return val
    return ""


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0

    prompt = _extract_prompt(data)
    if not prompt:
        return 0

    keywords = _load_keywords()
    if not keywords:
        return 0

    prompt_lower = prompt.lower()
    matched = [kw for kw in keywords if kw.lower() in prompt_lower]
    if not matched:
        return 0

    sample = ", ".join(matched[:5])
    sys.stdout.write(
        f"[Proposal Classify Gate] 检测到关键词: {sample}\n"
        "Art.5.4 要求会话首次非平凡 Edit/Write 前必须先跑 /proposal classify。\n"
        "Multi-phase / 架构级 / schema 迁移 / cross-clone 等场景"
        "即使在 own scope 内也必须 classify（参考 P-0056 教训）。\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
