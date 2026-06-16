# -*- coding: utf-8 -*-
"""
Claude Code UserPromptSubmit hook: constitution-reminder.py

Injects a brief constitutional reminder on every user message.
This is a system-level enforcement that prevents mid-conversation
drift from Article 0 (ritual) and Article 14 (phase wrap-up).

Exit code: always 0 (informational only, never blocks).
"""
import json
import sys


def main():
    """Output constitutional reminder on every user prompt."""
    try:
        json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, EOFError):
        pass

    print(
        "[Constitution] "
        "Art.0: first line must be the ritual. "
        "Art.14: run /wrap-up after each phase commit."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
