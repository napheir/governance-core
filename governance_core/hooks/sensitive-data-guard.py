"""Claude Code PreToolUse hook: sensitive-data-guard.py

Blocks an Edit / Write whose new content carries a HIGH-severity secret --
a private key block, a cloud access key, a platform token. Conservative by
design: only near-certain credentials trigger a block, so ordinary editing
is never obstructed. Heuristic keyword/value matches (MEDIUM severity) are
left to the candidate-uplink scan, where the destination is a public repo.

Reuses the shared scanner `governance_core.sensitive_scan` -- the same
detection logic the P-0065 uplink path runs, no forked patterns.

Fail-open: if the scanner is unavailable the hook allows the write rather
than freezing editing -- this is a content safety net, not the
authorization gate (auth-guard.py already fails closed on a broken package).

Exit codes: 0 = clean (allow), 2 = secret detected (block).
"""
import json
import sys


def main() -> None:
    """Block the pending Edit/Write if its content carries a HIGH secret."""
    try:
        hook_input = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except Exception:
        sys.exit(0)

    if hook_input.get("tool_name", "") not in ("Edit", "Write"):
        sys.exit(0)
    tool_input = hook_input.get("tool_input", {})

    # The content about to land: Write.content, or Edit.new_string.
    content = ""
    if "content" in tool_input:
        content = tool_input["content"]
    elif "new_string" in tool_input:
        content = tool_input["new_string"]
    if not content:
        sys.exit(0)

    try:
        from governance_core.sensitive_scan import scan_text, HIGH
    except Exception:
        sys.exit(0)  # scanner unavailable -> do not obstruct (fail-open)

    findings = scan_text(content, min_severity=HIGH)
    if findings:
        hit = findings[0]
        sys.stderr.write(
            f"[SENSITIVE DATA GUARD] BLOCKED: content carries a likely "
            f"secret -- {hit.pattern} (line {hit.line}).\n"
            f"  {hit.excerpt}\n"
            "  Remove the credential or move it to an untracked config file "
            "/ environment variable before writing.\n")
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
