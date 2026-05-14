"""UserPromptSubmit hook: warn (stderr) when avg cache_read crosses threshold.

Per proposals/prefix_cost_optimization.md Change B (approved 2026-05-07).

Output channel is stderr only -- stdout from UserPromptSubmit hooks gets
injected into the prompt as a system reminder, which would itself add prefix
bytes and partially defeat the purpose. stderr is shown to the user in their
terminal but does NOT enter the cached prefix.

The model is not the audience for this nudge -- the user is. When avg
cache_read over the last WINDOW assistant turns crosses THRESHOLD, the user
sees a one-line stderr message and can choose to /compact proactively.

Logic is fail-open: any parse error / missing file -> exit 0 (no warning, no
block). This is informational, not security.
"""
import json
import os
import sys
from collections import deque

THRESHOLD = 600_000
WINDOW = 10
MIN_TURNS_BEFORE_FIRING = 20


def main() -> int:
    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        return 0
    transcript_path = data.get("transcript_path", "")
    if not transcript_path or not os.path.isfile(transcript_path):
        return 0
    if "/subagents/" in transcript_path.replace("\\", "/"):
        return 0

    crs: deque = deque(maxlen=WINDOW)
    n_asst = 0
    try:
        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if (
                    '"type":"assistant"' not in line
                    and '"type": "assistant"' not in line
                ):
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("type") != "assistant":
                    continue
                u = (d.get("message") or {}).get("usage") or {}
                cr = int(u.get("cache_read_input_tokens") or 0)
                crs.append(cr)
                n_asst += 1
    except Exception:
        return 0

    if n_asst < MIN_TURNS_BEFORE_FIRING or len(crs) < WINDOW:
        return 0
    avg = sum(crs) / len(crs)
    if avg < THRESHOLD:
        return 0

    sys.stderr.write(
        f"[CacheWatchdog] avg cache_read = {avg/1e3:.0f}k over last {WINDOW} turns "
        f"(threshold {THRESHOLD/1e3:.0f}k). Consider /compact to reset prefix.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
