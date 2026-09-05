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
from pathlib import Path

#: Bytes used for each length prefix. Eight is far more than any field here
#: needs and costs nothing.
_LENGTH_BYTES = 8

#: Read size for :func:`file_digest`. Large enough that a 60 MB bundle is a
#: handful of reads, small enough that nothing is held in memory.
_FILE_CHUNK_BYTES = 1 << 20


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


def file_digest(path: Path) -> str:
    """Plain SHA-256 over the bytes of one file.

    The exception to both rules above, and the exception is the point.

    A release artefact's hash has to be **reproducible by the person holding
    the file**, with ``Get-FileHash -Algorithm SHA256`` or ``sha256sum`` and
    nothing else (ADR-0010 9). A domain prefix would make this repository the
    only place the number could be checked, which is the opposite of what
    publishing it is for. And the second rule has nothing to bite on here:
    length prefixes disambiguate a *tuple* of fields, and this is one file
    with no neighbours to be confused with.

    It lives in this module rather than in a new one because ADR-0010 9 says
    so: one place in this product computes digests.

    What the value proves is written next to it wherever it is published, and
    it is deliberately narrow (ADR-0009 11, carried forward): a hash
    identifies file integrity. It does not say the contents are correct or
    useful, and on an **unsigned** artefact it does not say who produced it
    either - the hash travels the same channel the file did.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_FILE_CHUNK_BYTES):
            hasher.update(chunk)
    return hasher.hexdigest()


__all__ = ["domain_digest", "domain_digest_bytes", "file_digest"]
