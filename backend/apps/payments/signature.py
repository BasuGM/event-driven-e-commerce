"""Stripe-style webhook signatures: ``<Name>-Signature: t=<unix seconds>,v1=<hex>[,v1=<hex>]``.

``v1 = HMAC-SHA256(secret, f"{t}." + raw_body)``. Signing the timestamp with the body means a
captured request can't be replayed later with a new ``t``, and the tolerance window bounds how
long a captured one stays valid. Several ``v1`` values are allowed so a secret can be rotated.
"""

from __future__ import annotations

import hashlib
import hmac
import time


class InvalidSignature(Exception):
    """Deliberately vague message: nothing in the response should help forge a signature."""


def compute(secret: str, timestamp: int, raw_body: bytes) -> str:
    return hmac.new(secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256).hexdigest()


def sign(secret: str, raw_body: bytes, *, timestamp: int | None = None) -> str:
    """Header value for ``raw_body`` (used by the fake provider when it delivers)."""
    t = int(time.time()) if timestamp is None else timestamp
    return f"t={t},v1={compute(secret, t, raw_body)}"


def verify(header: str | None, raw_body: bytes, secret: str, *, tolerance: int, now: float | None = None) -> int:
    """Return the signed timestamp, or raise InvalidSignature.

    The HMAC is over the raw bytes as received: never over re-serialised JSON.
    """
    if not header or not secret:
        raise InvalidSignature("invalid signature")
    timestamp, signatures = None, []
    for part in header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t" and value.isdigit():
            timestamp = int(value)
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise InvalidSignature("invalid signature")
    now = time.time() if now is None else now
    if abs(now - timestamp) > tolerance:
        raise InvalidSignature("invalid signature")
    expected = compute(secret, timestamp, raw_body)
    # compare_digest on each candidate: the time taken doesn't reveal how much of a guess matched
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise InvalidSignature("invalid signature")
    return timestamp
