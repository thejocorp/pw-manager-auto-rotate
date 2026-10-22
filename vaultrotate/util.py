"""Small helpers shared across vaultrotate: fingerprints, random values, backup names.

A secret value is never printed or logged. To tell whether two copies match, compare their
fingerprints (the first 12 hex of a SHA-256) instead of the values themselves.
"""
from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime


def fingerprint(value: str | None) -> str:
    """A short, non-reversible marker for a value. Safe to print."""
    if value is None:
        return "-"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def same(a: str | None, b: str | None) -> bool:
    if a is None or b is None:
        return False
    return hashlib.sha256(a.encode()).digest() == hashlib.sha256(b.encode()).digest()


def random_value(nbytes: int = 32, alphabet: str | None = None) -> str:
    """A fresh random secret. URL-safe by default; pass an alphabet for a custom one."""
    if alphabet:
        return "".join(secrets.choice(alphabet) for _ in range(nbytes))
    return secrets.token_urlsafe(nbytes)


def hex_value(nbytes: int = 32) -> str:
    return secrets.token_hex(nbytes)


def backup_suffix() -> str:
    return ".bak-" + datetime.now().strftime("%Y%m%d-%H%M%S")


DIGITS = string.digits
ALNUM = string.ascii_letters + string.digits
