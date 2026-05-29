"""Glob-to-regex matcher for proposal classify paths (P-0076).

gitignore-style semantics:
  * matches any chars except /
  ** matches any chars including /
  ? matches single char except /

Used by tools/proposal_lib.py classify --quick and .claude/hooks/proposal-classify-fast.py.
"""
import re
from functools import lru_cache


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern:
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "*":
            if i + 1 < n and pattern[i + 1] == "*":
                if i + 2 < n and pattern[i + 2] == "/":
                    out.append("(?:.*/)?")
                    i += 3
                    continue
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c == "?":
            out.append("[^/]")
            i += 1
            continue
        out.append(re.escape(c))
        i += 1
    return re.compile("^" + "".join(out) + "$")


def match(path: str, pattern: str) -> bool:
    """Match POSIX-style path against gitignore-style glob."""
    return _compile(pattern).match(path) is not None
