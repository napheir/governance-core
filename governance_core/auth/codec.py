"""Authorization-code codec for governance-core (P-0065 Phase 1, P-0071).

Auth-code format (single copy-pasteable line):

    GC1.<b64url(payload_json)>.<b64url(signature)>

`payload_json` is canonical JSON -- `json.dumps(obj, sort_keys=True,
separators=(",", ":"))`, UTF-8. `signature` is the Ed25519 signature over the
exact payload_json bytes.

Two payload schemas coexist:

  schema 1 (P-0065, legacy perpetual):
      {"consumer_id": str, "issued": "YYYY-MM-DD", "schema": 1,
       "expiry"?: "YYYY-MM-DD"}

  schema 2 (P-0071, leased + revocable):
      {"consumer_id": str, "issued": "YYYY-MM-DD", "schema": 2,
       "expiry": "YYYY-MM-DD", "revocation_feed_url": str,
       "max_offline_days": int}

`expiry` (ISO date): present and strictly before the reference date ->
verification fails; absent (schema 1 only) -> the code never expires.
`revocation_feed_url` is the signed revocation feed `auth-guard` polls;
`max_offline_days` bounds how long a consumer may run without a successful
feed fetch before it is frozen. Both are required for schema 2 and consumed
by the runtime `auth-guard` hook (P-0071 Phase 3), not by this codec.
"""

from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path
from typing import Any

from governance_core import auth

AUTH_CODE_PREFIX = "GC1"
# Schemas this codec can verify. New codes are issued at CURRENT_SCHEMA;
# schema 1 stays accepted so a self-hosted upgrade is never interrupted
# mid-transition (constitution Art.8 -- the dogfood instance must not break).
SUPPORTED_SCHEMAS = (1, 2)
CURRENT_SCHEMA = 2
# Keys a schema-2 payload must carry beyond the schema-1 core.
_SCHEMA2_REQUIRED = ("expiry", "revocation_feed_url", "max_offline_days")
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
                      expiry: str | None = None, *,
                      schema: int = 1,
                      revocation_feed_url: str | None = None,
                      max_offline_days: int | None = None) -> bytes:
    """Build the canonical-JSON payload bytes for an authorization code.

    `schema` selects the payload shape. Schema 1 carries an optional
    `expiry`. Schema 2 requires `expiry`, `revocation_feed_url`, and
    `max_offline_days` -- a missing one raises ValueError before signing.
    """
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError(f"unsupported payload schema: {schema!r}")
    obj: dict[str, Any] = {
        "consumer_id": consumer_id,
        "issued": issued,
        "schema": schema,
    }
    if schema == 2:
        if expiry is None or revocation_feed_url is None \
                or max_offline_days is None:
            raise ValueError(
                "schema-2 payload requires expiry, revocation_feed_url, "
                "and max_offline_days")
        if not isinstance(max_offline_days, int) or max_offline_days <= 0:
            raise ValueError("max_offline_days must be a positive integer")
        obj["expiry"] = expiry
        obj["revocation_feed_url"] = revocation_feed_url
        obj["max_offline_days"] = max_offline_days
    elif expiry is not None:
        obj["expiry"] = expiry
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def make_auth_code(payload: bytes, seed: bytes) -> str:
    """Sign `payload` with `seed` and return the GC1 authorization code."""
    sig = auth.sign(payload, seed)
    return f"{AUTH_CODE_PREFIX}.{b64url_encode(payload)}.{b64url_encode(sig)}"


def decode_payload(code: str) -> dict[str, Any]:
    """Decode a GC1 code's payload dict WITHOUT verifying the signature.

    For reading fields (consumer_id, revocation_feed_url, ...) off a code
    whose signature has separately been checked -- or whose verdict was
    cached as valid. The result MUST NOT be trusted on its own; an unsigned
    or tampered code can carry any payload. Raises AuthCodeError only when
    the code is structurally unparseable.
    """
    parts = code.strip().split(".")
    if len(parts) != 3 or parts[0] != AUTH_CODE_PREFIX:
        raise AuthCodeError(
            "malformed authorization code (expected GC1.<payload>.<sig>)")
    try:
        return json.loads(b64url_decode(parts[1]).decode("utf-8"))
    except (ValueError, TypeError, UnicodeDecodeError,
            json.JSONDecodeError) as exc:
        raise AuthCodeError(f"cannot decode authorization payload: {exc}")


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
    verify, the payload schema is unknown, a schema-2 payload is missing a
    required field, or the code has expired. `today` overrides the expiry
    reference date (ISO string) for testing.
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
    schema = payload.get("schema")
    if schema not in SUPPORTED_SCHEMAS:
        raise AuthCodeError(
            f"unsupported authorization payload schema: {schema!r}"
        )
    if "consumer_id" not in payload or not payload["consumer_id"]:
        raise AuthCodeError("authorization payload missing consumer_id")
    if schema == 2:
        missing = [k for k in _SCHEMA2_REQUIRED if k not in payload]
        if missing:
            raise AuthCodeError(
                f"schema-2 authorization payload missing field(s): {missing}"
            )
        if not payload["revocation_feed_url"]:
            raise AuthCodeError("schema-2 payload has empty revocation_feed_url")
        mod = payload["max_offline_days"]
        if not isinstance(mod, int) or isinstance(mod, bool) or mod <= 0:
            raise AuthCodeError(
                "schema-2 payload max_offline_days must be a positive integer"
            )
    if "expiry" in payload:
        reference = today or datetime.date.today().isoformat()
        if str(payload["expiry"]) < reference:
            raise AuthCodeError(
                f"authorization code expired on {payload['expiry']}"
            )
    return payload
