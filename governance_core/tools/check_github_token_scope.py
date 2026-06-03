"""check_github_token_scope.py -- verify the active gh token lacks delete_repo.

Root-cause defense (P-0097, gc #85). Repo deletion via ANY token-based path -- gh CLI
(`gh repo delete`), raw REST/GraphQL (`gh api`), curl, or an SDK script
(PyGithub / Octokit) -- requires the GitHub `delete_repo` OAuth scope. The
`repo` scope alone does NOT permit deletion. So if the active token lacks
`delete_repo`, GitHub rejects every deletion attempt regardless of how it is
issued. command-guard's deny patterns are fast pre-emptive feedback; THIS is
the airtight layer. This tool surfaces a loud warning if `delete_repo` ever
appears, so the red line stays visible. Wired into `governance-core doctor`
(P-0097, gc #85): doctor runs it best-effort and loud-warns on delete_repo,
without failing the install-health check.

Exit codes:
  0 = safe (no delete_repo) OR gh unavailable / unparseable (cannot verify)
  1 = delete_repo scope present -- repo deletion is POSSIBLE

The token value is never printed; only the scope list is surfaced.
"""
import re
import subprocess
import sys


def main() -> int:
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=20,
            encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sys.stderr.write(
            "[token-scope] gh unavailable; cannot verify delete_repo absence\n")
        return 0

    # gh prints the status block (incl. "Token scopes:") to stderr.
    combined = (result.stdout or "") + (result.stderr or "")
    match = re.search(r"Token scopes:\s*(.+)", combined)
    if not match:
        sys.stderr.write(
            "[token-scope] could not parse 'Token scopes:' from gh auth status "
            "(not logged in?)\n")
        return 0

    scopes = match.group(1).strip()
    if re.search(r"\bdelete_repo\b", scopes):
        sys.stderr.write(
            "[token-scope] *** RED LINE *** active gh token HAS 'delete_repo' "
            "scope -- repository deletion is POSSIBLE. Re-auth to a scope set "
            "WITHOUT delete_repo. Scopes: %s\n" % scopes)
        return 1

    sys.stdout.write(
        "[token-scope] OK: active gh token lacks delete_repo (repo deletion "
        "blocked at GitHub's authz layer). Scopes: %s\n" % scopes)
    return 0


if __name__ == "__main__":
    sys.exit(main())
