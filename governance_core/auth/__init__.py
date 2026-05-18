"""governance-core authorization primitives (P-0065).

Ed25519 keypair / sign / verify built on the vendored pure-Python
implementation (`_ed25519`). The installer verifies authorization codes with
`verify`; the maintainer signing tools issue them with `sign`. The auth-code
wire format lives in `codec`.
"""

from __future__ import annotations

import os

from governance_core.auth import _ed25519

SEED_BYTES = 32
PUBLIC_KEY_BYTES = 32
SIGNATURE_BYTES = 64


def generate_seed() -> bytes:
    """Return a fresh 32-byte Ed25519 secret seed from the OS CSPRNG."""
    return os.urandom(SEED_BYTES)


def public_key_from_seed(seed: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key from a secret seed."""
    if len(seed) != SEED_BYTES:
        raise ValueError(f"seed must be {SEED_BYTES} bytes, got {len(seed)}")
    return _ed25519.publickey(seed)


def sign(message: bytes, seed: bytes) -> bytes:
    """Sign `message` with `seed`; return the 64-byte Ed25519 signature."""
    if len(seed) != SEED_BYTES:
        raise ValueError(f"seed must be {SEED_BYTES} bytes, got {len(seed)}")
    public_key = _ed25519.publickey(seed)
    return _ed25519.signature(message, seed, public_key)


def verify(message: bytes, signature: bytes, public_key: bytes) -> bool:
    """Return True iff `signature` is a valid Ed25519 signature of `message`."""
    if len(signature) != SIGNATURE_BYTES or len(public_key) != PUBLIC_KEY_BYTES:
        return False
    try:
        return _ed25519.checkvalid(signature, message, public_key)
    except ValueError:
        return False
