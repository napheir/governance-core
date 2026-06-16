# -*- coding: utf-8 -*-
"""
direction-guard.py - PostToolUse direction drift detector
---------------------------------------------------------
Fires after Edit/Write operations. Uses a timestamp file to throttle:
only outputs a direction-check reminder every 30 minutes of active work.

Reads STATE.md "Updates in This Session" section to extract current goals,
then reminds the agent to verify alignment.

Non-blocking (always exit 0). Informational only.

Hypothesis: Models drift from stated goals during long sessions (>30 min).
This compensates by periodically surfacing the original objective.
Created: 2026-04-05
Model assumption: All current models (Opus 4.6, Sonnet 4.6)
Review schedule: Quarterly (next: 2026-07-05)
"""
import io
import json
import os
import sys
import time

# Force UTF-8 output on Windows (avoid GBK encoding errors per Art.7 rule 7)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --- Configuration ---
CHECK_INTERVAL_SECONDS = 30 * 60  # 30 minutes
TIMESTAMP_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), ".direction_check_ts"
)
STATE_FILE = "STATE.md"
MAX_GOAL_LINES = 8  # Max lines to extract from STATE.md header


def should_check() -> bool:
    """Return True if enough time has passed since last direction check."""
    if not os.path.isfile(TIMESTAMP_FILE):
        return True
    try:
        with open(TIMESTAMP_FILE, "r") as f:
            last_ts = float(f.read().strip())
        return (time.time() - last_ts) >= CHECK_INTERVAL_SECONDS
    except (ValueError, OSError):
        return True


def update_timestamp() -> None:
    """Record current time as last direction check."""
    try:
        with open(TIMESTAMP_FILE, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def extract_current_goals() -> str:
    """Extract the first session update entry from STATE.md."""
    if not os.path.isfile(STATE_FILE):
        return "(STATE.md not found)"

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return "(STATE.md unreadable)"

    # Find "## 1. Updates in This Session" then the first ### heading
    in_updates = False
    goal_lines = []
    for line in lines:
        stripped = line.strip()
        if "Updates in This Session" in stripped:
            in_updates = True
            continue
        if in_updates:
            if stripped.startswith("### "):
                if goal_lines:
                    break  # Next entry, stop
                goal_lines.append(stripped)
                continue
            if goal_lines:
                if stripped.startswith("## "):
                    break  # Next major section
                goal_lines.append(stripped)
                if len(goal_lines) >= MAX_GOAL_LINES:
                    break

    if not goal_lines:
        return "(no current session goals found)"
    return "\n".join(goal_lines[:MAX_GOAL_LINES])


def main() -> None:
    """Check direction alignment on a throttled schedule."""
    # Parse PostToolUse event from stdin
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    # Only process Edit/Write completions
    tool_name = event.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    if not should_check():
        sys.exit(0)

    # Time to check direction
    goals = extract_current_goals()
    update_timestamp()

    elapsed_min = CHECK_INTERVAL_SECONDS // 60
    sys.stdout.write(
        f"[direction-guard] {elapsed_min}+ min since last direction check.\n"
        f"Current STATE.md goal:\n{goals}\n\n"
        "-> Verify: is your current work aligned with this goal? "
        "If you have drifted, pause and re-orient before continuing.\n"
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
