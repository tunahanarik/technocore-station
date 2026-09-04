"""The secret-pattern scan that runs before an evidence row is written.

The charter asks for one (16.1) and nothing implemented it.
:func:`station_api.logging_setup.redact` is not it: that is an exact-match
registry of values this process minted, with no notion of what a secret
*looks* like, so a seed that arrived from somewhere else passes through it
untouched.

Refuse, do not redact
---------------------
The obvious design - scrub the offending run and store the rest - is wrong
here, and wrong in a way that is easy to miss. The evidence is the **raw
bytes**: the exported line re-verifies against the signature only because it
is byte-exact, and a redacted byte is a byte that was changed. Redacting
would turn evidence into something that looks like evidence and verifies
against nothing. So a hit refuses the write, says so, and leaves the send
result untouched - the message was sent either way, and pretending otherwise
would be a second lie on top of the first (ADR-0003 8).

Order is the whole design: allow-list first
-------------------------------------------
A signed message body is *made* of high-entropy public values. An 86-character
base64url signature contains 43-character base64url runs and can contain
64-character hex runs; a ``did:key`` is 56 characters of base58. Running the
deny rules first would refuse every single record this product produces, and
the natural "fix" for that - loosening the deny rules until real traffic
passes - is how a scanner ends up detecting nothing.

The allow-list is a set of **values**, not a set of shapes
----------------------------------------------------------
The first version allowed a token because it *looked* like a signature, a DID
or a nonce, and then never looked inside it. Three probes walked straight
through that:

* a 64-hex seed contains no ``0``, so it is a valid base58btc tail: append it
  to ``did:key:z`` and the DID rule allowed the token, canary and all;
* a 43-character seed padded to 86 base64url characters is the signature
  shape exactly, so the signature rule allowed it;
* the hex rule's boundary lookarounds meant a **65**-character hex run
  matched nothing at all.

The third was a bug in one regex. The first two are not fixable by tightening
a shape, because at 86 base64url characters a padded seed and a real
signature are the same shape - there is no property of the token that tells
them apart. What tells them apart is *provenance*: the caller knows which DID,
signature and nonce this record is made of, because it produced them.

So :func:`require_no_secrets` takes the public values explicitly. A token is
skipped when it **is** one of them, byte for byte - and a declared value is
itself checked against the public shapes first, so a caller cannot launder a
seed by declaring it. Everything else in the text reaches the deny rules, and
the deny rules now match runs of *at least* the secret length rather than
exactly it, so padding no longer hides anything.

The deny rules, and what each one is for
----------------------------------------
* a value registered with the log redactor - a live vault passphrase or CSRF
  token that reached a string it should never have reached;
* a run of 64 **or more** hex characters - a raw 32-byte seed or private key
  in the spelling ``seed_import`` accepts, with or without padding. A SHA-256
  digest has the same shape and is public, and it is **still refused**: none
  of the fields scanned here - the canonical message text, the request body,
  the response body - has any business carrying a bare digest, and the ADR's
  answer to a false positive is to refuse and say so rather than to carve out
  an exception that a real seed could then be dressed up as;
* a run of 43 **or more** base64url characters - the same 32 bytes in the
  spelling this project's own envelopes use, again with or without padding.

A false positive refuses the write and reports which rule fired
(``docs/evidence-model.md``). That is deliberately annoying: a user who sees
it can look at their own message and decide, and a scanner that silently let
one through would have no such moment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from technocore_conform import (
    DID_KEY_PREFIX,
    MAX_NONCE_DIGITS,
    MULTIBASE_LENGTH,
    NONCE_PATTERN,
    SIGNATURE_PATTERN,
)

from station_api.logging_setup import contains_registered_secret

#: One token: the character classes that appear inside a base64url run, a hex
#: run, a nonce and a ``did:key``. Splitting anywhere else would cut a DID in
#: half at its colons and hand the deny rules a fragment.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_:.\-]+")

#: The canonical signature shape, taken from the engine that produces it
#: rather than restated: 86 characters, base64url, last character in
#: ``AQgw`` because the trailing four bits of a 64-byte value are zero.
#: The engine publishes these patterns unanchored, because they are embedded
#: in larger expressions elsewhere. Anchored here: a *substring* that looks
#: like a signature does not make the surrounding token public.
_ALLOW_SIGNATURE = re.compile(rf"\A{SIGNATURE_PATTERN}\Z")

#: ``did:key:z`` plus a base58btc multibase tail of the **exact** published
#: length. The earlier ``{1,64}`` was three characters of slack away from a
#: catastrophe: base58btc excludes ``0``, so a 64-hex seed with no zero in it
#: is a valid 64-character tail, and the bound stopped at exactly 64.
_ALLOW_DID = re.compile(
    rf"\A{re.escape(DID_KEY_PREFIX)}z[1-9A-HJ-NP-Za-km-z]{{{MULTIBASE_LENGTH - 1}}}\Z"
)

#: 1-19 digits, from the same engine, anchored for the same reason.
_ALLOW_NONCE = re.compile(rf"\A{NONCE_PATTERN}\Z")

#: A raw 32-byte value in hex, anywhere inside a token. ``{64,}`` rather than
#: ``{64}``: with an exact count the boundary lookarounds cancel each other
#: out and a 65-character run matches nothing, which is the opposite of what
#: a longer run should mean.
_DENY_HEX64_RUN = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64,}(?![0-9A-Fa-f])")

#: A raw 32-byte value in unpadded base64url, anywhere inside a token. Also
#: ``{43,}``: padding a 43-character seed out to 86 characters must not turn
#: it into something this rule declines to look at.
_DENY_B64URL_RUN = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43,}(?![A-Za-z0-9_-])")

#: Length of the base64url spelling of 32 bytes, unpadded.
SEED_B64URL_CHARS = 43

#: Length of the hex spelling of 32 bytes.
SEED_HEX_CHARS = 64


class SecretRule(StrEnum):
    """Which deny rule fired. Named so a refusal can be explained."""

    REGISTERED_VALUE = "registered_value"
    HEX_64 = "hex_64"
    BASE64URL_43 = "base64url_43"


#: One sentence per rule, safe to show. None of them echoes the offending
#: value: a refusal that printed the secret would be the leak it prevented.
RULE_DETAIL: dict[SecretRule, str] = {
    SecretRule.REGISTERED_VALUE: (
        "Kanit yazilmadi: metin, bu surecin urettigi ve asla kaydedilmemesi "
        "gereken bir degeri iceriyor."
    ),
    SecretRule.HEX_64: (
        f"Kanit yazilmadi: metinde en az {SEED_HEX_CHARS} karakterlik bir hex "
        "dizisi var. Bu bir seed veya ozel anahtar uzunlugudur. Yanlis alarm "
        "olsa bile kanit redakte edilerek saklanmaz - ham baytlari degistirmek "
        "onu kanit olmaktan cikarir."
    ),
    SecretRule.BASE64URL_43: (
        f"Kanit yazilmadi: metinde en az {SEED_B64URL_CHARS} karakterlik bir "
        "base64url dizisi var. Bu bir seed uzunlugudur. Yanlis alarm olsa bile "
        "kanit redakte edilerek saklanmaz."
    ),
}


class SecretPatternRefusedError(Exception):
    """A secret-shaped value was found. The write is refused, not redacted."""

    def __init__(self, rule: SecretRule, *, where: str) -> None:
        super().__init__(f"{where}: {RULE_DETAIL[rule]}")
        self.rule = rule
        self.where = where


@dataclass(frozen=True, slots=True)
class ScanFinding:
    """One reason a write was refused. Never carries the offending value."""

    rule: SecretRule
    where: str

    @property
    def detail(self) -> str:
        return RULE_DETAIL[self.rule]


def is_public_protocol_value(token: str) -> bool:
    """True for the shapes this protocol publishes in the clear.

    No longer a licence to skip a token: it is the check a **declared** public
    value has to pass before :func:`declared_public_values` will honour it. A
    caller that handed in a seed as though it were a signature gets nothing,
    because a seed is 43 or 64 characters and none of these shapes is.
    """
    if _ALLOW_SIGNATURE.match(token) is not None:
        return True
    if _ALLOW_DID.match(token) is not None:
        return True
    return _ALLOW_NONCE.match(token) is not None and len(token) <= MAX_NONCE_DIGITS


def declared_public_values(values: frozenset[str]) -> frozenset[str]:
    """The subset of ``values`` that really is public protocol data.

    Declaring a value is a claim about provenance; passing a public shape is
    a claim about form. Both are required, so neither a caller's mistake nor
    a caller's compromise can whitelist a secret on its own.
    """
    return frozenset(value for value in values if is_public_protocol_value(value))


def scan_text(
    text: str, *, where: str, public_values: frozenset[str] = frozenset()
) -> ScanFinding | None:
    """The first finding in ``text``, or ``None``.

    ``public_values`` are the exact strings the caller knows to be public
    protocol data for this record - its DID, its signature, its nonce. A token
    equal to one of them is skipped; anything else is looked inside.

    Returns rather than raises so a caller can collect findings across
    several fields and report all of them; :func:`require_no_secrets` is the
    fail-closed wrapper the write path uses.
    """
    if contains_registered_secret(text):
        return ScanFinding(rule=SecretRule.REGISTERED_VALUE, where=where)

    allowed = declared_public_values(public_values)
    for token in _TOKEN_RE.findall(text):
        if token in allowed:
            continue
        if _DENY_HEX64_RUN.search(token) is not None:
            return ScanFinding(rule=SecretRule.HEX_64, where=where)
        if _DENY_B64URL_RUN.search(token) is not None:
            return ScanFinding(rule=SecretRule.BASE64URL_43, where=where)
    return None


def scan_bytes(
    payload: bytes, *, where: str, public_values: frozenset[str] = frozenset()
) -> ScanFinding | None:
    """Scan bytes by decoding leniently.

    ``errors="replace"`` rather than a strict decode: a byte sequence that is
    not UTF-8 must still be scanned, and refusing to look at it would be a
    hole shaped exactly like "send the seed as latin-1".
    """
    return scan_text(
        payload.decode("utf-8", errors="replace"),
        where=where,
        public_values=public_values,
    )


def require_no_secrets(
    fields: dict[str, str | bytes], *, public_values: frozenset[str] = frozenset()
) -> None:
    """Fail closed over every field about to be written.

    ``public_values`` is the record's own DID, signature and nonce - the only
    high-entropy values a signed body legitimately contains, and the only ones
    this scan will step over. Omitting it scans everything, which is the right
    default for a caller that does not know what it is holding.

    Raises :class:`SecretPatternRefusedError` on the first finding. The exception
    message names the field and the rule and never the value.
    """
    for where, value in fields.items():
        finding = (
            scan_bytes(value, where=where, public_values=public_values)
            if isinstance(value, bytes)
            else scan_text(value, where=where, public_values=public_values)
        )
        if finding is not None:
            raise SecretPatternRefusedError(finding.rule, where=finding.where)


__all__ = [
    "RULE_DETAIL",
    "SEED_B64URL_CHARS",
    "SEED_HEX_CHARS",
    "ScanFinding",
    "SecretPatternRefusedError",
    "SecretRule",
    "declared_public_values",
    "is_public_protocol_value",
    "require_no_secrets",
    "scan_bytes",
    "scan_text",
]
