"""Sensitive-data (secret) scanner for governance-core (P-0065 Phase 4).

One pattern-based scanner, shared by two consumers:

  - the `sensitive-data-guard` PreToolUse hook -- blocks an Edit / Write
    whose content carries a HIGH-severity secret;
  - the candidate uplink path -- refuses to publish a candidate envelope to
    a public repository when its payload carries a HIGH- or MEDIUM-severity
    secret.

Patterns are split by severity so the hook stays conservative (HIGH only --
near-zero false positives, never obstructs ordinary editing) while the
uplink stays cautious (HIGH + MEDIUM, because the destination is public).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

HIGH = "high"
MEDIUM = "medium"


@dataclass(frozen=True)
class Finding:
    """One secret-pattern hit in scanned text."""

    pattern: str
    severity: str
    line: int
    excerpt: str


# (name, severity, compiled regex). HIGH patterns are shaped tightly enough
# that a match is almost certainly a real credential. MEDIUM patterns are
# heuristic (keyword + quoted value) and may false-positive on examples.
_PATTERNS: list[tuple[str, str, "re.Pattern[str]"]] = [
    ("private key block", HIGH,
     re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("AWS access key id", HIGH, re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub token", HIGH, re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", HIGH, re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,}\b")),
    ("Google API key", HIGH, re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("secret assignment", MEDIUM, re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|access[_-]?key)\b"
        r"\s*[:=]\s*['\"][^'\"\s]{8,}['\"]")),
]


def _redact(text: str) -> str:
    """Return a short, value-masked excerpt safe to print in a report."""
    snippet = text.strip()[:80]
    return re.sub(r"[A-Za-z0-9_\-+/]{12,}", "<redacted>", snippet)


def scan_text(text: str, min_severity: str = HIGH) -> list[Finding]:
    """Scan `text` for secrets; return findings at or above `min_severity`.

    `min_severity` is HIGH (only definite secrets) or MEDIUM (also the
    heuristic keyword/value matches).
    """
    want_medium = min_severity == MEDIUM
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, severity, pattern in _PATTERNS:
            if severity == MEDIUM and not want_medium:
                continue
            if pattern.search(line):
                findings.append(Finding(name, severity, lineno, _redact(line)))
    return findings


def scan_file(path: Path, min_severity: str = HIGH) -> list[Finding]:
    """Scan a file's text for secrets. Unreadable / binary files yield []."""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return scan_text(text, min_severity=min_severity)
