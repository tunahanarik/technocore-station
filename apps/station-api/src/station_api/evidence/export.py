"""Deterministic evidence export, in JSON and in Markdown.

Three properties, and each one is a decision rather than a detail.

**Consent is structural.** :class:`ExportConsent` cannot be constructed
without an explicit acknowledgement, and the export functions take one. There
is no default argument, no ``confirm: bool = True`` and no route that skips
it: an export without consent is not refused at runtime so much as
unrepresentable in the call graph (charter 15.6, ADR-0003 9).

**The bytes are deterministic - unconditionally.** The same records produce
the same file, byte for byte, on every run: JSON goes through
:func:`~station_api.strict_json.canonical_json_bytes` (sorted keys, no
whitespace, already pinned by a test vector) and the Markdown writer emits
fixed sections in a fixed order with ``\\n`` line endings. A user who exports
twice and diffs sees nothing, so that a difference means something.

The word that had to be earned there is *unconditionally*. The first version
stamped ``exported_at`` into both documents, so two exports of an unchanged
archive were never identical and the promise had a footnote nobody reading
the file would know about. The stamp now travels in a response header
(``X-Station-Exported-At``) instead of in the body. That is the choice that
makes the claim true without qualification rather than the choice that
rewrites the claim to fit the code - and nothing is lost, because when the
export happened is not a fact about the evidence: it is a fact about the
copy, the audit chain already records it as an event, and every record in the
file carries its own ``recorded_at``.

**Imported text is neutralised, and nothing is dropped.**
``safe_display`` sweeps control, format and separator characters - and also
truncates at two hundred characters, which is right for a log line and wrong
for a document that is supposed to be the archive. It escapes no markup at
all, because it was written for storing and comparing values, not for
embedding them in a markup language. A message body is *user and network*
text: it can carry ``[click](javascript:...)``, a raw ``<img onerror=...>``,
a table row that breaks the surrounding table, or a fence that turns the rest
of the document into code.

So Markdown gets its own escaper, applied to every value. It sweeps
(invisible characters become a space - a visible one, never a deletion),
escapes every metacharacter, and truncates nothing: an export that silently
shortened a message body would be an archive of something the user did not
send. The JSON writer needs no escaper, because JSON has no markup.

**Forbidden phrases are checked on our sentences, not on the file.** See
:mod:`station_api.evidence.language`. Scanning the finished document meant a
message body - or a remote error excerpt quoted in ``capture_detail`` - could
refuse both export formats permanently, which is the archive being locked by
the very text it exists to keep.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from station_api.evidence.language import assert_no_forbidden_claim
from station_api.evidence.records import LEVEL_4_ABSENT, LEVEL_NAMES, EvidenceView
from station_api.evidence.states import CAPTURE_DETAIL
from station_api.strict_json import b64u_encode, canonical_json_bytes
from station_api.technocore.projection import sweep_untrusted

#: The two formats. A closed set: a third would be a third writer to keep
#: deterministic and a third escaping problem to get right.
ExportFormat = Literal["json", "markdown"]

EXPORT_FORMATS: tuple[ExportFormat, ...] = ("json", "markdown")

#: Suffix per format, used to build the download name.
EXPORT_SUFFIX: dict[str, str] = {"json": ".json", "markdown": ".md"}

EXPORT_MEDIA_TYPE: dict[str, str] = {
    # ``charset`` is stated rather than left to the client: a Markdown file
    # full of Turkish read as latin-1 is a different document.
    "json": "application/json; charset=utf-8",
    "markdown": "text/markdown; charset=utf-8",
}

#: The schema version of the exported document. Bumped when the shape
#: changes, so an old file is never read under new rules.
EXPORT_VERSION = 1

EXPORT_KIND = "technocore-station.evidence-export"

#: Characters Markdown gives meaning to. Every one of them is escaped in
#: every interpolated value, including the ones that only matter at the start
#: of a line - deciding per position is how an escaper acquires a bug.
_MARKDOWN_SPECIALS = "\\`*_{}[]()#+-.!|<>&~"

_MARKDOWN_RE = re.compile("([" + re.escape(_MARKDOWN_SPECIALS) + "])")

#: The honest sentence about what the audit chain provides. The only wording
#: permitted for it (``docs/evidence-model.md`` 2).
CHAIN_SENTENCE = (
    "Audit zinciri cevrimdisi degisiklige karsi tespit edicidir. Ayni Windows "
    "kullanicisi olarak calisan bir saldirgana, guvenilir bir zamana veya "
    "ucuncu bir tarafa ispata karsilik gelmez."
)

#: The sentence naming what the Markdown summary does **not** carry. Absence
#: is stated rather than left for a reader to discover by not finding
#: something - the same rule level 4 is written under.
MARKDOWN_SCOPE_NOTE = (
    "Bu ozet insan okumasi icindir. Ham baytlar - yakalanan satir, cevre "
    "penceresi, istek ve yanit govdesi - yalnizca JSON bicimindedir; burada "
    "onlarin SHA-256 degerleri vardir. Imzanin kapsadigi kanonik metin her iki "
    "bicimde de tam olarak yazilir."
)

#: What the export says when a room has been seen under more than one epoch.
GENERATION_CHANGED_NOTE = (
    "Oda birden fazla generation altinda gorulmustur; iki taraf ayni donemden "
    "degildir ve karsilastirilamaz."
)

#: Every sentence **this product itself writes** into an export, as opposed to
#: every string that ends up in one. Checked before a file is built. A room
#: name, a message body and a remote error excerpt are deliberately absent:
#: they are data, they are escaped, and they may not refuse a file. The short
#: field labels the writers interpolate are covered statically instead - see
#: ``test_evidence_language.py``, which walks every string literal in this
#: package - because a label like ``"DID"`` cannot carry a claim and listing
#: thirty of them here would only invite the two lists to drift.
PRODUCT_SENTENCES: tuple[str, ...] = (
    CHAIN_SENTENCE,
    LEVEL_4_ABSENT,
    MARKDOWN_SCOPE_NOTE,
    GENERATION_CHANGED_NOTE,
    *LEVEL_NAMES,
    *CAPTURE_DETAIL.values(),
)


class ExportRefusedError(Exception):
    """An export was attempted without consent, or with an unknown format."""


@dataclass(frozen=True, slots=True)
class ExportConsent:
    """Proof that a person asked for this file.

    Constructed only through :meth:`granted`, which takes ``Literal[True]``.
    ``ExportConsent()`` is a type error and ``granted(False)`` raises, so
    there is no spelling of "export anyway" that type-checks *and* runs.
    """

    acknowledged: bool
    requested_at: datetime

    @classmethod
    def granted(cls, *, acknowledged: Literal[True], now: datetime) -> ExportConsent:
        if acknowledged is not True:
            raise ExportRefusedError(
                "Disa aktarim acik onay ister. Onay verilmeden dosya "
                "uretilmez."
            )
        return cls(acknowledged=True, requested_at=now)


def escape_markdown(value: str) -> str:
    """Make an untrusted value inert inside a Markdown document.

    Swept first - every control, format, surrogate, private-use and separator
    character becomes a **space**, so a newline cannot break out of a table
    row and a right-to-left override cannot reorder what the reader sees -
    then every Markdown metacharacter is backslash-escaped. The order matters:
    escaping first and sweeping afterwards could remove a backslash and re-arm
    the character it was protecting.

    ``<`` and ``&`` are escaped as well, because Markdown renderers pass raw
    HTML through by default; an evidence file that renders an ``<img>`` from
    a captured message body is an evidence file that fetches something.

    ``sweep_untrusted`` rather than ``safe_display``: the latter also truncates
    at two hundred characters and strips the ends, which is right for a log
    line and wrong here. Every value written into an export is bounded already
    - a message by the protocol's own limit, a capture sentence by
    ``MAX_DETAIL_CHARS`` - and an archive that quietly shortened one of them
    would be an archive of something the user did not send. Nothing is
    dropped: characters are substituted or escaped, never deleted.
    """
    return _MARKDOWN_RE.sub(r"\\\1", sweep_untrusted(value))


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _record_document(view: EvidenceView) -> dict[str, Any]:
    """One record, as plain JSON-able data. Bytes become base64url."""
    return {
        "id": view.id,
        "reservation_id": view.reservation_id,
        "room": view.room,
        "levels": {
            "1_imza_kaniti": {
                "present": view.signature_verified,
                "did": view.did,
                "nonce": view.nonce,
                "canonical": view.canonical,
                "canonical_sha256": view.canonical_sha256,
                "signature": view.signature,
            },
            "2_sunucu_gozlemi": {
                "present": view.capture_state == "line_captured",
                "capture_state": view.capture_state,
                "capture_detail": view.capture_detail,
                "captured_at": _iso(view.captured_at),
                "export_url": view.export_url,
                # Three separate facts. The baseline epoch, the epoch the
                # stored line was actually read under, and whether the room
                # has ever been seen under more than one - written apart so a
                # line can never be reported beside an epoch it did not come
                # from.
                "room_generation": view.room_generation,
                "capture_generation": view.capture_generation,
                "generation_changed": view.generation_changed,
                "captured_line_b64url": (
                    None if view.captured_line is None else b64u_encode(view.captured_line)
                ),
                "captured_line_offset": view.captured_line_offset,
                "captured_line_length": view.captured_line_length,
                "window_b64url": [b64u_encode(line) for line in view.captured_window],
                "stream_sha256": view.stream_sha256,
                "stream_bytes": view.stream_bytes,
                "stream_truncated": view.stream_truncated,
                "stream_line_count": view.stream_line_count,
                "unreadable_lines": view.unreadable_lines,
                "request_b64url": b64u_encode(view.request_body),
                "request_sha256": view.request_sha256,
                "response_b64url": b64u_encode(view.response_body),
                "response_sha256": view.response_sha256,
                "http_status": view.http_status,
                "write_outcome": view.write_outcome,
            },
            "3_yerel_kayit_zamani": {
                "present": True,
                "recorded_at": _iso(view.recorded_at),
            },
            # Written, and written as null. An omitted key would read as an
            # oversight; null reads as the decision it is.
            "4_harici_anchor": {
                "present": False,
                "value": view.external_anchor,
                "detail": LEVEL_4_ABSENT,
            },
        },
    }


def assert_product_language(*, where: str) -> None:
    """Refuse to write a file if one of *our own* sentences over-claims.

    Every string in :data:`PRODUCT_SENTENCES` is text this product authored,
    so a forbidden phrase in one of them is a wording bug and fails closed.
    The finished document is deliberately **not** scanned: it also contains a
    message body and a remote error excerpt, and letting either of those
    refuse the file locked whole archives permanently, in both formats, on
    every retry (see :mod:`station_api.evidence.language`).
    """
    for sentence in PRODUCT_SENTENCES:
        assert_no_forbidden_claim(sentence, where=where)


def build_json_export(
    records: Sequence[EvidenceView], *, consent: ExportConsent
) -> bytes:
    """The JSON export. Canonical, so the same input gives the same bytes.

    No ``exported_at`` key: the request time is returned in a response header
    instead, so that two exports of an unchanged archive are byte-identical
    with no footnote (see the module docstring).
    """
    _require_consent(consent)
    assert_product_language(where="json export")
    document = {
        "kind": EXPORT_KIND,
        "version": EXPORT_VERSION,
        "record_count": len(records),
        "audit_chain": CHAIN_SENTENCE,
        "records": [_record_document(view) for view in records],
    }
    return canonical_json_bytes(document)


def _markdown_record(view: EvidenceView, index: int) -> list[str]:
    esc = escape_markdown
    captured = view.capture_state == "line_captured"
    return [
        f"## {index}. Kayit - {esc(view.room)}",
        "",
        "| Alan | Deger |",
        "| --- | --- |",
        f"| Kayit id | `{esc(view.id)}` |",
        f"| Rezervasyon | `{esc(view.reservation_id)}` |",
        f"| Oda | `{esc(view.room)}` |",
        f"| Nonce | `{esc(view.nonce)}` |",
        f"| Gonderim sonucu | `{esc(view.write_outcome)}` |",
        f"| HTTP | `{view.http_status}` |",
        "",
        "### Seviye 1 - Imza kaniti",
        "",
        f"- Durum: {'dolu' if view.signature_verified else 'bos'}",
        f"- DID: `{esc(view.did)}`",
        f"- Imza: `{esc(view.signature)}`",
        # The string the signature was taken over. It was in the JSON export
        # and not here, which made this format a summary that could not be
        # checked against anything - and nothing but oversight put it there:
        # it is text, it is bounded by the protocol's own message limit, and
        # it goes through the same escaper as every other value.
        f"- Kanonik metin: `{esc(view.canonical)}`",
        f"- Kanonik metin SHA-256: `{esc(view.canonical_sha256)}`",
        "",
        "### Seviye 2 - Sunucu gozlemi",
        "",
        f"- Durum: {'dolu' if captured else 'bos'}",
        f"- Yakalama sonucu: `{esc(view.capture_state or 'denenmedi')}`",
        f"- Aciklama: {esc(view.capture_detail)}",
        f"- Generation (ilk gorulen): `{esc(view.room_generation or 'yok')}`",
        f"- Yakalanan satirin generation'i: `{esc(view.capture_generation or 'yok')}`",
        *(
            [f"- {escape_markdown(GENERATION_CHANGED_NOTE)}"]
            if view.generation_changed
            else []
        ),
        f"- Satir offset/uzunluk: `{view.captured_line_offset}` / "
        f"`{view.captured_line_length}`",
        f"- Akis SHA-256: `{esc(view.stream_sha256 or 'yok')}`",
        f"- Taranan bayt: `{view.stream_bytes}`"
        # The digest covers what was read. At the cap that is the scanned
        # prefix, and the note beside it has to say so.
        + (
            " (tarama tavana dayandi; SHA-256 taranan onege aittir)"
            if view.stream_truncated
            else ""
        ),
        f"- Okunamayan satir: `{view.unreadable_lines}`",
        f"- Istek SHA-256: `{esc(view.request_sha256)}`",
        f"- Yanit SHA-256: `{esc(view.response_sha256)}`",
        "",
        "### Seviye 3 - Yerel kayit zamani",
        "",
        f"- `{esc(view.recorded_at.isoformat())}`",
        "",
        "### Seviye 4 - Harici anchor",
        "",
        f"- `null` - {esc(LEVEL_4_ABSENT)}",
        "",
    ]


def build_markdown_export(
    records: Sequence[EvidenceView], *, consent: ExportConsent
) -> bytes:
    """The Markdown export. Fixed sections, fixed order, ``\\n`` endings.

    A **summary**, and it now says so in the file. The text the two formats
    carry is the same - the canonical string a signature covers is in both,
    because a summary nothing can be re-verified from is decoration - but the
    raw bytes stay in the JSON export alone. Base64 blobs in a document meant
    to be read would cost it its only advantage without making it more
    complete than the format that already holds them, so the difference is
    written down rather than left to be noticed.
    """
    _require_consent(consent)
    assert_product_language(where="markdown export")
    lines: list[str] = [
        "# Technocore Station - kanit disa aktarimi",
        "",
        f"- Bicim surumu: `{EXPORT_VERSION}`",
        f"- Kayit sayisi: `{len(records)}`",
        "",
        f"> {escape_markdown(CHAIN_SENTENCE)}",
        "",
        f"> {escape_markdown(MARKDOWN_SCOPE_NOTE)}",
        "",
    ]
    if not records:
        lines += ["Bu disa aktarimda kayit yok.", ""]
    for index, view in enumerate(records, start=1):
        lines += _markdown_record(view, index)

    return "\n".join(lines).encode("utf-8")


def _require_consent(consent: ExportConsent) -> None:
    if not isinstance(consent, ExportConsent) or consent.acknowledged is not True:
        raise ExportRefusedError(
            "Disa aktarim acik onay ister. Onay verilmeden dosya uretilmez."
        )


def build_export(
    records: Sequence[EvidenceView],
    *,
    export_format: ExportFormat,
    consent: ExportConsent,
) -> bytes:
    if export_format == "json":
        return build_json_export(records, consent=consent)
    if export_format == "markdown":
        return build_markdown_export(records, consent=consent)
    raise ExportRefusedError(f"Bilinmeyen disa aktarim bicimi: {export_format!r}")


__all__ = [
    "CHAIN_SENTENCE",
    "EXPORT_FORMATS",
    "EXPORT_KIND",
    "EXPORT_MEDIA_TYPE",
    "EXPORT_SUFFIX",
    "EXPORT_VERSION",
    "GENERATION_CHANGED_NOTE",
    "MARKDOWN_SCOPE_NOTE",
    "PRODUCT_SENTENCES",
    "ExportConsent",
    "ExportFormat",
    "ExportRefusedError",
    "assert_product_language",
    "build_export",
    "build_json_export",
    "build_markdown_export",
    "escape_markdown",
]
