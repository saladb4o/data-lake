"""Process-independent identifiers for records that must dedupe across runs.

Python's built-in `hash()` of a str is salted per process (PYTHONHASHSEED),
so `f"press_{abs(hash(link))}"` produces a different id for the same article
on every restart. Anything keyed on those ids - the news lake, the disclosure
store, the BCTC document cache - therefore stops recognising records it has
already stored, and the same item accumulates under a new id each time the
server comes up.

crc32 is not a cryptographic hash and is not meant to be one. It is stable,
cheap, and identical in every process and on every machine, which is the only
property an identity key needs here.
"""

from __future__ import annotations

import zlib
from typing import Any

__all__ = ["stable_hash", "stable_id"]


def stable_hash(key: Any, modulo: int | None = None) -> int:
    """A deterministic non-negative integer digest of ``key``.

    Args:
        key: Anything with a stable ``str()``. Callers should pass the natural
            identity of the record (a URL, a title plus date), not an object
            whose repr embeds a memory address.
        modulo: Optional bound; the digest is reduced into ``[0, modulo)``.
            Reducing raises the collision rate, so only bound it when a short
            id genuinely matters.
    """
    digest = zlib.crc32(str(key).encode("utf-8"))
    return digest % modulo if modulo else digest


def stable_id(prefix: str, key: Any, modulo: int | None = None) -> str:
    """``prefix`` joined to :func:`stable_hash` of ``key`` by an underscore."""
    return f"{prefix}_{stable_hash(key, modulo)}"
