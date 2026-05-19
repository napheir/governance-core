"""Version parsing + comparison for governance-core (P-0073).

governance-core release versions are clean dotted integers (X.Y.Z). This
module parses and compares them -- shared by the update-reminder hook
(P-0073 Phase 1) and the `upgrade --dry-run` version delta (Phase 2), so
the comparison logic lives in one unit-testable place rather than inline
in a hyphen-named hook script.
"""

from __future__ import annotations


def parse_version(text: str) -> tuple[int, ...] | None:
    """Parse a dotted version string into an int tuple, or None if malformed.

    A non-string, or any component that is not an integer, yields None --
    callers treat None as "cannot compare" and stay silent rather than
    misreport.
    """
    if not isinstance(text, str):
        return None
    try:
        parsed = tuple(int(part) for part in text.strip().split("."))
    except ValueError:
        return None
    return parsed or None


def is_newer(candidate: str, baseline: str) -> bool:
    """Return True iff `candidate` is a strictly newer version than `baseline`.

    A malformed version on either side yields False -- never claim an
    update is available on un-parseable input.
    """
    c = parse_version(candidate)
    b = parse_version(baseline)
    if c is None or b is None:
        return False
    return c > b


def minor_gap(newer: str, older: str) -> int:
    """Return how many (major, minor) steps `newer` is ahead of `older`.

    Counts a major bump as crossing into a new minor line too. Returns 0
    when `newer` is not ahead, or on un-parseable input. Used by the
    `upgrade --dry-run` version-skew warning (P-0073 Phase 2).
    """
    n = parse_version(newer)
    o = parse_version(older)
    if n is None or o is None or n <= o:
        return 0
    n_mm = (n + (0, 0))[:2]
    o_mm = (o + (0, 0))[:2]
    if n_mm[0] != o_mm[0]:
        return max(1, (n_mm[0] - o_mm[0]) * 1)
    return n_mm[1] - o_mm[1]
