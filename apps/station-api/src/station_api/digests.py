"""Domain-separated digests over structured values.

Small, dependency-free, and shared by everything that has to say "these
exact fields, in this exact order, mean this exact thing".

Two rules, both learned the hard way elsewhere in this codebase:

* **Domain separation.** A digest is only meaningful against the purpose it
  was computed for. Every caller names its own domain and version, so a
  digest built for one binding can never be presented as another.
* **Length prefixes, not separators.** Joining fields with a separator lets
  a field that contains the separator impersonate a different tuple of
  fields - ``("ab", "c")`` and ``("a", "bc")`` hash alike. Prefixing each
  field with its byte length removes the ambiguity rather than relying on
  the fields never containing the separator.
"""

from __future__ import annotations

import hashlib

#: Bytes used for each length prefix. Eight is far more than any field here
#: needs and costs nothing.
_LENGTH_BYTES = 8


def domain_digest_bytes(domain: bytes, *parts: bytes) -> str:
    """SHA-256 over ``domain`` and each part, length-prefixed, in order."""
    hasher = hashlib.sha256()
    hasher.update(domain)
    for part in parts:
        hasher.update(len(part).to_bytes(_LENGTH_BYTES, "big"))
        hasher.update(part)
    return hasher.hexdigest()


def domain_digest(domain: bytes, *parts: str) -> str:
    """The same, for text fields, encoded as UTF-8."""
    return domain_digest_bytes(domain, *(part.encode("utf-8") for part in parts))


__all__ = ["domain_digest", "domain_digest_bytes"]
