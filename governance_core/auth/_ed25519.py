"""Vendored pure-Python Ed25519 (RFC 8032) -- zero runtime dependency.

This is the public-domain reference implementation of the Ed25519 signature
scheme (Bernstein et al.). It is deliberately the slow, recursive reference
form: governance-core signs one tiny payload at code-issue time and verifies
one signature at install time, so performance is irrelevant and auditable
correctness is what matters (P-0065 Phase 0 locked this over a crypto
dependency).

Provenance: the algorithm is the well-known reference `ed25519.py` placed in
the public domain by the Ed25519 authors. Type hints and docstrings were
added for code-standard compliance (constitution Art.7); the arithmetic is
unchanged.

Not constant-time. Acceptable here: signing happens offline on the
maintainer's own machine and verification handles no secret. Do not reuse
this module for high-rate or adversarial-timing-sensitive contexts.
"""

from __future__ import annotations

import hashlib

_B = 256
_Q = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493


def _sha512(m: bytes) -> bytes:
    """Return the SHA-512 digest of `m`."""
    return hashlib.sha512(m).digest()


def _expmod(b: int, e: int, m: int) -> int:
    """Return `b ** e mod m` via square-and-multiply."""
    if e == 0:
        return 1
    t = _expmod(b, e // 2, m) ** 2 % m
    if e & 1:
        t = (t * b) % m
    return t


def _inv(x: int) -> int:
    """Return the multiplicative inverse of `x` modulo the field prime."""
    return _expmod(x, _Q - 2, _Q)


_D = -121665 * _inv(121666)
_I = _expmod(2, (_Q - 1) // 4, _Q)


def _xrecover(y: int) -> int:
    """Recover the x-coordinate on the curve for a given y-coordinate."""
    xx = (y * y - 1) * _inv(_D * y * y + 1)
    x = _expmod(xx, (_Q + 3) // 8, _Q)
    if (x * x - xx) % _Q != 0:
        x = (x * _I) % _Q
    if x % 2 != 0:
        x = _Q - x
    return x


_BY = 4 * _inv(5)
_BX = _xrecover(_BY)
_BASE = [_BX % _Q, _BY % _Q]


def _edwards(p: list[int], q: list[int]) -> list[int]:
    """Add two points `p` and `q` on the twisted Edwards curve."""
    x1, y1 = p[0], p[1]
    x2, y2 = q[0], q[1]
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _D * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _D * x1 * x2 * y1 * y2)
    return [x3 % _Q, y3 % _Q]


def _scalarmult(p: list[int], e: int) -> list[int]:
    """Return the scalar multiple `e * p` on the Edwards curve."""
    if e == 0:
        return [0, 1]
    q = _scalarmult(p, e // 2)
    q = _edwards(q, q)
    if e & 1:
        q = _edwards(q, p)
    return q


def _encodeint(y: int) -> bytes:
    """Encode integer `y` as a little-endian 32-byte string."""
    bits = [(y >> i) & 1 for i in range(_B)]
    return bytes(
        sum(bits[i * 8 + j] << j for j in range(8)) for i in range(_B // 8)
    )


def _encodepoint(p: list[int]) -> bytes:
    """Encode curve point `p` as a 32-byte string."""
    x, y = p[0], p[1]
    bits = [(y >> i) & 1 for i in range(_B - 1)] + [x & 1]
    return bytes(
        sum(bits[i * 8 + j] << j for j in range(8)) for i in range(_B // 8)
    )


def _bit(h: bytes, i: int) -> int:
    """Return bit `i` (little-endian) of byte string `h`."""
    return (h[i // 8] >> (i % 8)) & 1


def publickey(sk: bytes) -> bytes:
    """Derive the 32-byte Ed25519 public key from a 32-byte secret seed."""
    h = _sha512(sk)
    a = 2 ** (_B - 2) + sum(2 ** i * _bit(h, i) for i in range(3, _B - 2))
    point = _scalarmult(_BASE, a)
    return _encodepoint(point)


def _hint(m: bytes) -> int:
    """Return SHA-512 of `m` interpreted as a little-endian integer."""
    h = _sha512(m)
    return sum(2 ** i * _bit(h, i) for i in range(2 * _B))


def signature(m: bytes, sk: bytes, pk: bytes) -> bytes:
    """Sign message `m` with secret seed `sk` and matching public key `pk`."""
    h = _sha512(sk)
    a = 2 ** (_B - 2) + sum(2 ** i * _bit(h, i) for i in range(3, _B - 2))
    r = _hint(h[_B // 8:_B // 4] + m)
    big_r = _scalarmult(_BASE, r)
    s = (r + _hint(_encodepoint(big_r) + pk + m) * a) % _L
    return _encodepoint(big_r) + _encodeint(s)


def _isoncurve(p: list[int]) -> bool:
    """Return True if point `p` lies on the Edwards curve."""
    x, y = p[0], p[1]
    return (-x * x + y * y - 1 - _D * x * x * y * y) % _Q == 0


def _decodeint(s: bytes) -> int:
    """Decode a little-endian byte string into an integer."""
    return sum(2 ** i * _bit(s, i) for i in range(0, _B))


def _decodepoint(s: bytes) -> list[int]:
    """Decode a 32-byte string into a curve point; raise ValueError if invalid."""
    y = sum(2 ** i * _bit(s, i) for i in range(0, _B - 1))
    x = _xrecover(y)
    if x & 1 != _bit(s, _B - 1):
        x = _Q - x
    point = [x, y]
    if not _isoncurve(point):
        raise ValueError("decoding point that is not on curve")
    return point


def checkvalid(s: bytes, m: bytes, pk: bytes) -> bool:
    """Return True iff signature `s` is valid for message `m` under key `pk`.

    Raises ValueError if `s` or `pk` has the wrong length.
    """
    if len(s) != _B // 4:
        raise ValueError("signature length is wrong")
    if len(pk) != _B // 8:
        raise ValueError("public-key length is wrong")
    try:
        big_r = _decodepoint(s[0:_B // 8])
        big_a = _decodepoint(pk)
    except ValueError:
        return False
    s_int = _decodeint(s[_B // 8:_B // 4])
    h = _hint(_encodepoint(big_r) + pk + m)
    return _scalarmult(_BASE, s_int) == _edwards(big_r, _scalarmult(big_a, h))
