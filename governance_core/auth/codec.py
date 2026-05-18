"""Authorization-code codec for governance-core (P-0065 Phase 1).

Auth-code format (single copy-pasteable line):

    GC1.<b64url(payload_json)>.<b64url(signature)>

`payload_json` is canonical JSON -- `json.dumps(obj, sort_keys=True,
separators=(",", ":"))`, UTF-8 -- of:

    {"consumer_id": str, "issued": "YYYY-MM-DD", "schema": 1, "expiry"?: "..."}

`signature` is the Ed25519 signature over the exact payload_json bytes.
`expiry` (ISO date) is optional: present and in the past -> verification
fails; absent -> the code never expires.
"""

from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path
from typing import Any

from governance_core import auth

AUTH_CODE_PREFIX = "GC1"
PAYLOAD_SCHEMA = 1
_PUBKEY_PATH = Path(__file__).resolve().parent / "pubkey.json"


class AuthCodeError(Exception):
    """Raised when an authorization code is malformed, unsigned, or expired."""


def b64url_encode(raw: bytes) -> str:
    """Base64url-encode `raw` without padding."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    """Base64url-decode `text`, restoring stripped padding."""
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def canonical_payload(consumer_id: str, issued: str,
                      expiry: str | None = None) -> bytes:
    """Build the canonical-JSON payload bytes for an authorization code."""
    obj: dict[str, Any] = {
        "consumer_id": consumer_id,
        "issued": issued,
        "schema": PAYLOAD_SCHEMA,
    }
    if expiry is not None:
        obj["expiry"] = expiry
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def make_auth_code(payload: bytes, seed: bytes) -> str:
    """Sign `payload` with `seed` and return the GC1 authorization code."""
    sig = auth.sign(payload, seed)
    return f"{AUTH_CODE_PREFIX}.{b64url_encode(payload)}.{b64url_encode(sig)}"


def load_bundled_public_key() -> bytes:
    """Return the 32-byte Ed25519 public key shipped inside the package."""
    if not _PUBKEY_PATH.exists():
        raise AuthCodeError(
            f"package public key missing: {_PUBKEY_PATH} "
            "(governance-core build is incomplete)"
        )
    data = json.loads(_PUBKEY_PATH.read_text(encoding="utf-8"))
    return b64url_decode(data["key_b64"])


def verify_auth_code(code: str, public_key: bytes,
                     today: str | None = None) -> dict[str, Any]:
    """Verify `code` against `public_key`; return its payload dict.

    Raises AuthCodeError if the code is malformed, the signature does not
    verify, the payload schema is unknown, or the code has expired. `today`
    overrides the expiry reference date (ISO string) for testing.
    """
    parts = code.strip().split(".")
    if len(parts) != 3 or parts[0] != AUTH_CODE_PREFIX:
        raise AuthCodeError(
            "malformed authorization code (expected GC1.<payload>.<sig>)"
        )
    try:
        payload_bytes = b64url_decode(parts[1])
        sig = b64url_decode(parts[2])
    except (ValueError, TypeError) as exc:
        raise AuthCodeError(f"authorization code is not valid base64url: {exc}")
    if not auth.verify(payload_bytes, sig, public_key):
        raise AuthCodeError("authorization code signature does not verify")
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthCodeError(f"authorization payload is not valid JSON: {exc}")
    if payload.get("schema") != PAYLOAD_SCHEMA:
        raise AuthCodeError(
            f"unsupported authorization payload schema: {payload.get('schema')!r}"
        )
    if "consumer_id" not in payload or not payload["consumer_id"]:
        raise AuthCodeError("authorization payload missing consumer_id")
    if "expiry" in payload:
        reference = today or datetime.date.today().isoformat()
        if str(payload["expiry"]) < reference:
            raise AuthCodeError(
                f"authorization code expired on {payload['expiry']}"
            )
    return payload
