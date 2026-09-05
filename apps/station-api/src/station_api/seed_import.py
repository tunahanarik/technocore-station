"""Parsing the official seed format.

The only format Station accepts is the one the pinned official signer
actually uses. Reading ``vendor/technocore-reference/scripts/sign.py``, key
material reaches it through ``--seed`` / ``$SIGN_SEED`` in one of two ways:

    64 hex characters -> used directly as the 32-byte Ed25519 seed
    anything else     -> SHA-256 of the string (a passphrase)

Station supports **only the first**. The passphrase branch is refused, because
the project brief forbids deriving a seed from a password: it turns a
32-byte random secret into whatever entropy the phrase happened to have.

``keygen`` prints its result as ``seed: <64 hex>``, so a file holding that
line is also accepted - it is literally the official tool's own output.
Nothing else is guessed at.
"""

from __future__ import annotations

import re

#: An official seed is 32 bytes written as 64 hex characters. The count is
#: enforced by the two regexes below; a second spelling of 64 would only be
#: a place for the two to drift apart.
SEED_LENGTH = 32

#: A seed file is tiny. Refuse anything that could be a pasted keystore.
MAX_SEED_FILE_BYTES = 8 * 1024

_BARE_HEX_RE = re.compile(r"\A[0-9a-fA-F]{64}\Z")

#: The exact shape `sign.py keygen` prints.
_KEYGEN_LINE_RE = re.compile(r"^seed:[ \t]*([0-9a-fA-F]{64})[ \t]*$", re.MULTILINE)


class SeedImportError(ValueError):
    """The file is not an official seed file.

    The message never contains the file contents or the path.
    """


def parse_official_seed(payload: bytes) -> bytes:
    """Extract the 32-byte seed from an official seed file.

    Accepts a bare 64-hex value (with surrounding whitespace) or the
    ``seed: <hex>`` line produced by ``sign.py keygen``. Everything else is
    refused, including the passphrase form.
    """
    if len(payload) > MAX_SEED_FILE_BYTES:
        raise SeedImportError("Seed dosyasi beklenenden buyuk; resmi bir seed dosyasi degil.")

    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SeedImportError("Seed dosyasi UTF-8 metin olmalidir.") from exc

    stripped = text.strip()

    if _BARE_HEX_RE.match(stripped):
        return bytes.fromhex(stripped)

    matches = _KEYGEN_LINE_RE.findall(text)
    if len(matches) == 1:
        return bytes.fromhex(matches[0])
    if len(matches) > 1:
        raise SeedImportError("Dosyada birden fazla seed satiri var; tek bir seed bekleniyor.")

    raise SeedImportError(
        "Desteklenen bicim bulunamadi. Yalniz 64 hex karakterlik resmi seed "
        "veya keygen ciktisindaki seed satiri kabul edilir. "
        "Paroladan seed turetme bu urunde bilerek desteklenmez."
    )


__all__ = [
    "MAX_SEED_FILE_BYTES",
    "SEED_LENGTH",
    "SeedImportError",
    "parse_official_seed",
]
