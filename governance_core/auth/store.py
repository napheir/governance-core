"""Authorization-code storage (P-0132).

The project's authorization code lives in `.governance/auth_code` -- one
line, the code itself -- which the installer's managed .gitignore block
ignores. It used to sit in `.governance/config.json` (`authorization.
auth_code`), a git-tracked file, which published the hub's own code in its
public repository. config.json keeps only the non-secret `consumer_id` and
`verified_at`.

This module is the one implementation of where the code is read and
written. It is stdlib-only because the installer also copies the whole auth
package beside the hooks as `_gc_auth`, and the fail-closed `auth-guard`
reads the code through that copy without importing governance_core.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

AUTH_CODE_REL = ".governance/auth_code"


class AuthStoreError(Exception):
    """Raised when the stored authorization code file is present but unusable."""


def code_path(project_root: Path) -> Path:
    """Return the path of the authorization-code file under `project_root`."""
    return Path(project_root) / AUTH_CODE_REL


def read_code(project_root: Path) -> str | None:
    """Return the stored authorization code, or None when no file exists.

    Raises:
        AuthStoreError: the file exists but is empty or unreadable.
    """
    path = code_path(project_root)
    if not path.is_file():
        return None
    try:
        code = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise AuthStoreError(f"cannot read {path}: {exc}") from None
    if not code:
        raise AuthStoreError(f"{path} is empty")
    return code


def write_code(project_root: Path, code: str) -> Path:
    """Atomically write `code` (plus a trailing LF) to the code file.

    Written via a temp file in the same directory and os.replace(), so a
    reader never sees a half-written code. Returns the file path.
    """
    path = code_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".auth_code.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(code.strip() + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
