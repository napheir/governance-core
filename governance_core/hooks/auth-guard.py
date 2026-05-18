"""Claude Code PreToolUse hook: auth-guard.py

Runtime authorization enforcement (P-0065 Phase 1). Fires before EVERY tool
call. If the project's governance-core authorization code is missing,
tampered, or no longer verifies against the bundled public key, this hook
blocks the tool call -- freezing the agent's ability to act in the project
until it is re-authorized.

This is the runtime half of the authorization gate. `install` / `upgrade`
gate materialization (no valid code -> the autonomy layer is never copied);
this hook gates continued use (a project whose code later becomes invalid
has its capabilities frozen). Together they make "invalid authorization ->
no capabilities" hold continuously, not only at install time.

Fail-closed: any error -- missing config, missing authorization block,
broken package, unreadable public key -- is treated as unauthorized and
blocks. A consumer recovers by re-running, from a terminal:

    governance-core install --auth-code <CODE>

The freeze affects the agent's tool calls only; the human's own shell is
unaffected, so recovery is always possible.

Verification is cached per (repo, code, public key, date) in the OS temp
dir so the Ed25519 verify runs once per code per day, not on every tool
call. The date is part of the cache key on purpose (P-0071): a code that
verified yesterday must be re-checked today, otherwise an expired code
would keep being served a stale `valid` verdict.

Exit codes:
  0 = authorized (allow)
  2 = unauthorized (block)
"""
import datetime
import hashlib
import json
import sys
import tempfile
from pathlib import Path

_BLOCK_HEADER = (
    "[AUTH GUARD] BLOCKED: governance-core authorization is invalid or "
    "missing -- all capabilities are disabled."
)
_BLOCK_RECOVER = (
    "  Recover: run  governance-core install --auth-code <CODE>  in a "
    "terminal (capabilities are gated on a valid maintainer-issued code; "
    "see README 'Authorization')."
)


def _block(detail: str) -> None:
    """Emit the block message with `detail` and exit 2 (deny the tool call)."""
    sys.stderr.write(f"{_BLOCK_HEADER}\n  Reason: {detail}\n{_BLOCK_RECOVER}\n")
    sys.exit(2)


def _verify(auth_code: str, public_key: bytes) -> bool:
    """Verify `auth_code` against `public_key`; return True iff valid."""
    from governance_core.auth import codec
    try:
        codec.verify_auth_code(auth_code, public_key)
        return True
    except codec.AuthCodeError:
        return False


def main() -> None:
    """Block the pending tool call unless governance-core is authorized."""
    # Consume the hook payload to keep the stdin protocol clean (unused).
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    # repo root: hook lives at <repo>/.claude/hooks/auth-guard.py
    root = Path(__file__).resolve().parent.parent.parent
    cfg_path = root / ".governance" / "config.json"

    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _block(f"cannot read .governance/config.json ({exc})")

    if "authorization" not in cfg or "auth_code" not in cfg["authorization"]:
        _block("no authorization recorded in config.json")
    auth_code = cfg["authorization"]["auth_code"]

    try:
        from governance_core.auth import codec
        public_key = codec.load_bundled_public_key()
    except Exception as exc:
        _block(f"governance-core package public key unavailable ({exc})")

    code_sha = hashlib.sha256(auth_code.encode("utf-8")).hexdigest()
    pub_sha = hashlib.sha256(public_key).hexdigest()
    root_tag = hashlib.sha256(str(root).encode("utf-8")).hexdigest()[:16]
    cache_path = Path(tempfile.gettempdir()) / f"gc_auth_{root_tag}.json"
    today = datetime.date.today().isoformat()

    # Cache hit: the verdict for this exact (code, public key, date) is
    # known. The date must match -- a verdict from a prior day is not
    # trusted, so an expired code is re-checked and blocked (P-0071).
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if (cached["code_sha256"] == code_sha
                and cached["pubkey_sha256"] == pub_sha
                and cached.get("verified_on") == today):
            if cached["valid"]:
                sys.exit(0)
            _block("authorization code does not verify (cached)")
    except Exception:
        pass  # no cache / stale cache / unreadable -> verify below

    valid = _verify(auth_code, public_key)
    try:
        cache_path.write_text(
            json.dumps({"code_sha256": code_sha, "pubkey_sha256": pub_sha,
                        "verified_on": today, "valid": valid}),
            encoding="utf-8",
        )
    except Exception:
        pass  # cache is an optimization; never fail the hook on it

    if valid:
        sys.exit(0)
    _block("authorization code does not verify")


if __name__ == "__main__":
    main()
