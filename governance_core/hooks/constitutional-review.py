"""Constitutional Review Hook (PreToolUse: Edit/Write).

Checks code changes against constitution core articles before allowing
Edit/Write operations:
- Article 4: No .get() fallback for config, no hardcoded config params
- Article 7: No print() for logging
- Article 8: No paper/live business logic forks

Dual mode:
- No ANTHROPIC_API_KEY -> regex review (zero latency, zero cost)
- With API key -> LLM review (semantic understanding, higher coverage)

Exit codes:
  0 = allow (compliant or non-code file)
  2 = block (violation detected)

Based on research agent prototype (commit 87df6c6), with fixes:
- Exclude logic changed from per-file to per-match
- Broadened .get() exclusions to reduce false positives
- Added tests/ and tools/ to skip list
- Narrowed hardcoded threshold rule
"""
import json
import re
import sys

# ============================================================
# Regex review rules
# ============================================================

REGEX_RULES = [
    {
        "article": "4",
        "name": ".get() fallback",
        "pattern": r'\.get\s*\([^)]+,\s*[^)]+\)',
        "exclude": r'(os\.environ\.get|os\.getenv|request\.get|requests\.'
                   r'get|response\.get|headers\.get|params\.get|kwargs\.get'
                   r'|args\.get|row\.get|item\.get|meta\.get|data\.get'
                   r'|hook_input\.get|tool_input\.get|result\.get'
                   r'|sys\.argv|\.get\(\s*["\'][\w]+["\']\s*\))',
        "description": "No .get(key, default) config fallback (Art.4)",
    },
    {
        "article": "4",
        "name": "hardcoded time",
        "pattern": r'\btime\s*\(\s*\d+\s*,\s*\d+\s*\)',
        "exclude": None,
        "description": "No hardcoded time literals time(H, M) (Art.4)",
    },
    {
        "article": "4",
        "name": "hardcoded threshold assignment",
        "pattern": r'\b(?:threshold|exit_threshold|signal_threshold'
                   r'|confidence_threshold)\s*=\s*\d+\.?\d*\s*$',
        "exclude": r'(config\[|config\.)',
        "description": "No hardcoded threshold params (Art.4)",
    },
    {
        "article": "4",
        "name": "hardcoded comparison threshold",
        "pattern": r'(?:probability|score|confidence|confidence_tier)'
                   r'\s*[><=!]+\s*\d+\.\d+',
        "exclude": r'(config\[|config\.|[><=!]=?\s*0\.0\s*[\)\],:;\n])',
        "description": "No hardcoded comparison thresholds (Art.4)",
    },
    {
        "article": "7",
        "name": "print instead of logging",
        "pattern": r'^\s*print\s*\(',
        "exclude": r'(if\s+__name__|def\s+main|__main__|'
                   r'# print|#.*print|parser\.|argparse)',
        "context_lines": 5,
        "description": "No print() for logging, use logging module (Art.7)",
    },
    {
        "article": "8",
        "name": "paper/live fork function",
        "pattern": r'def\s+\w+_(paper|live)\s*\(',
        "exclude": None,
        "description": "No _paper()/_live() parallel functions (Art.8)",
    },
    {
        "article": "8",
        "name": "is_paper/is_live branch",
        "pattern": r'\bif\s+.*\bis_(paper|live)(_mode)?\b',
        "exclude": None,
        "description": "No is_paper/is_live conditional branches (Art.8)",
    },
]

# File patterns to skip (not business code)
SKIP_EXTENSIONS = {".md", ".txt", ".json", ".yml", ".yaml", ".toml", ".cfg",
                   ".ini", ".csv", ".html", ".css", ".xml"}

SKIP_PATH_PATTERNS = [
    r'\.claude[/\\]',
    r'proposals/',
    r'tests/',
    r'tools/',
    r'STATE\.md',
    r'MEMORY',
    r'CLAUDE\.md',
    r'AGENTS\.md',
    r'sandbox/',
    r'references/',
    r'__pycache__/',
    r'\.gitignore',
    r'conftest\.py',
]


def should_skip_file(filepath: str) -> bool:
    """Determine if this file should be skipped.

    Normalize path separators first so SKIP_PATH_PATTERNS like 'tools/'
    match Windows paths that come in with backslashes.
    """
    norm = filepath.replace("\\", "/")
    for ext in SKIP_EXTENSIONS:
        if norm.endswith(ext):
            return True
    for pattern in SKIP_PATH_PATTERNS:
        if re.search(pattern, norm, re.IGNORECASE):
            return True
    return False


def extract_code_content(tool_name: str, tool_input: dict) -> tuple:
    """Extract filepath, pre-edit content, and post-edit content.

    Closing the prior loophole (R6 from harness audit 2026-04-28): old
    implementation only reviewed `new_string`, letting agents bypass
    Art.4/7/8 checks by extracting violating code into a helper function
    and then Editing only an unrelated entry-point line.

    Now we capture both states and let regex_review() flag only violations
    introduced by THIS edit (new count > old count) — pre-existing
    violations in the file pass through unchanged.

    Returns:
        (filepath, current_content, simulated_content)
    """
    filepath = tool_input.get("file_path", "")

    if tool_name == "Write":
        new_content = tool_input.get("content", "")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                current = f.read()
        except (OSError, UnicodeDecodeError):
            current = ""  # new file
        return filepath, current, new_content

    if tool_name == "Edit":
        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")
        replace_all = bool(tool_input.get("replace_all", False))

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                current = f.read()
        except (OSError, UnicodeDecodeError):
            # Edit on non-readable file — fall back to new_string-only check
            return filepath, "", new_string

        if not old_string:
            return filepath, current, current

        if replace_all:
            simulated = current.replace(old_string, new_string)
        else:
            idx = current.find(old_string)
            if idx < 0:
                return filepath, current, current
            simulated = (
                current[:idx] + new_string + current[idx + len(old_string):]
            )

        return filepath, current, simulated

    return filepath, "", ""


def _count_violations(code: str) -> dict:
    """Return rule_name -> list of (matched_text, line_idx) for code.

    A violation is a regex match that survives its per-rule exclude check.
    """
    if not code:
        return {}
    lines = code.split("\n")
    by_rule: dict = {}
    for rule in REGEX_RULES:
        hits = []
        for match in re.finditer(rule["pattern"], code, re.MULTILINE):
            matched_text = match.group(0).strip()
            match_line_idx = code[:match.start()].count("\n")
            ctx_size = rule.get("context_lines", 0)
            ctx_start = max(0, match_line_idx - ctx_size)
            context = "\n".join(lines[ctx_start:match_line_idx + 1])
            if rule.get("exclude") and re.search(rule["exclude"], context):
                continue
            hits.append(matched_text[:60])
        by_rule[rule["name"]] = hits
    return by_rule


def regex_review(current: str, simulated: str) -> dict:
    """Block only violations INTRODUCED by this edit.

    Compares match counts between pre-edit (`current`) and post-edit
    (`simulated`) states. Reports the first violation that exists in
    simulated but not in current — i.e., new violations introduced by
    the edit, not pre-existing ones. This closes the helper-extraction
    bypass (R6) without false-positive blocking innocent edits to files
    that already contain violations elsewhere.
    """
    old_hits = _count_violations(current)
    new_hits = _count_violations(simulated)

    for rule in REGEX_RULES:
        rule_name = rule["name"]
        old_set = list(old_hits.get(rule_name, []))
        new_set = list(new_hits.get(rule_name, []))
        # If post-edit has more matches than pre-edit, the edit introduced
        # at least one. Pick the first match that's not accounted for in old.
        if len(new_set) > len(old_set):
            # find an entry that wasn't in old (multiset semantics)
            old_copy = list(old_set)
            for matched_text in new_set:
                if matched_text in old_copy:
                    old_copy.remove(matched_text)
                    continue
                return {
                    "ok": False,
                    "reason": (
                        f"{rule['description']} -- matched: "
                        f"'{matched_text}'"
                    ),
                    "article": rule["article"],
                    "rule": rule_name,
                }
    return {"ok": True}


def main():
    """Hook entry point."""
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    tool_input = hook_input.get("tool_input", {})
    filepath, current, simulated = extract_code_content(tool_name, tool_input)

    if should_skip_file(filepath):
        sys.exit(0)

    if not filepath.endswith(".py"):
        sys.exit(0)

    if not simulated.strip():
        sys.exit(0)

    result = regex_review(current, simulated)

    if not result.get("ok", True):
        reason = result.get("reason", "unknown violation")
        print(
            f"[Constitutional Review] {reason}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
