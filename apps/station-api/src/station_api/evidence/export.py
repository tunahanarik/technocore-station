"""Deterministic evidence export, in JSON and in Markdown.

Three properties, and each one is a decision rather than a detail.

**Consent is structural.** :class:`ExportConsent` cannot be constructed
without an explicit acknowledgement, and the export functions take one. There
is no default argument, no ``confirm: bool = True`` and no route that skips
it: an export without consent is not refused at runtime so much as
unrepresentable in the call graph (charter 15.6, ADR-0003 9).

**The bytes are deterministic.** The same records produce the same file, byte
for byte, on every run: JSON goes through
:func:`~station_api.strict_json.canonical_json_bytes` (sorted keys, no
whitespace, already pinned by a test vector) and the Markdown writer emits
fixed sections in a fixed order with ``\\n`` line endings. A user who exports
twice and diffs should see nothing, so that a difference means something.

**Imported text is neutralised.** ``safe_display`` removes control, format
and separator characters - and that is all it removes. It does not escape
``<``, ``[``, ``](``, a backtick or a pipe, because it was written for
storing and comparing values, not for embedding them in a markup language.
A message body is *user and network* text: it can carry
``[click](javascript:...)``, a raw ``<img onerror=...>``, a table row that
breaks the surrounding table, or a fence that turns the rest of the document
into code. So Markdown gets its own escaper, applied to every value, and the
JSON writer needs none because JSON has no markup.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from station_api.evidence.language import assert_no_forbidden_claim
from station_api.evidence.records import LEVEL_4_ABSENT, EvidenceView
from station_api.strict_json import b64u_encode, canonical_json_bytes
from station_api.technocore.projection import safe_display

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

    Swept first - control, bidi and separator characters are removed by
    ``safe_display``, which is also what bounds the length - then every
    Markdown metacharacter is backslash-escaped. The order matters: escaping
    first and sweeping afterwards could remove a backslash and re-arm the
    character it was protecting.

    ``<`` and ``&`` are escaped as well, because Markdown renderers pass raw
    HTML through by default; an evidence file that renders an ``<img>`` from
    a captured message body is an evidence file that fetches something.
    """
    return _MARKDOWN_RE.sub(r"\\\1", safe_display(value))


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
                "room_generation": view.room_generation,
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


def build_json_export(
    records: Sequence[EvidenceView], *, consent: ExportConsent
) -> bytes:
    """The JSON export. Canonical, so the same input gives the same bytes."""
    _require_consent(consent)
    document = {
        "kind": EXPORT_KIND,
        "version": EXPORT_VERSION,
        "exported_at": consent.requested_at.isoformat(),
        "record_count": len(records),
        "audit_chain": CHAIN_SENTENCE,
        "records": [_record_document(view) for view in records],
    }
    payload = canonical_json_bytes(document)
    assert_no_forbidden_claim(payload.decode("utf-8"), where="json export")
    return payload


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
        f"- Kanonik metin SHA-256: `{esc(view.canonical_sha256)}`",
        "",
        "### Seviye 2 - Sunucu gozlemi",
        "",
        f"- Durum: {'dolu' if captured else 'bos'}",
        f"- Yakalama sonucu: `{esc(view.capture_state or 'denenmedi')}`",
        f"- Aciklama: {esc(view.capture_detail)}",
        f"- Generation: `{esc(view.room_generation or 'yok')}`",
        f"- Satir offset/uzunluk: `{view.captured_line_offset}` / "
        f"`{view.captured_line_length}`",
        f"- Akis SHA-256: `{esc(view.stream_sha256 or 'yok')}`",
        f"- Taranan bayt: `{view.stream_bytes}`"
        + (" (tarama tavana dayandi)" if view.stream_truncated else ""),
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
    """The Markdown export. Fixed sections, fixed order, ``\\n`` endings."""
    _require_consent(consent)
    lines: list[str] = [
        "# Technocore Station - kanit disa aktarimi",
        "",
        f"- Bicim surumu: `{EXPORT_VERSION}`",
        f"- Disa aktarim zamani: `{escape_markdown(consent.requested_at.isoformat())}`",
        f"- Kayit sayisi: `{len(records)}`",
        "",
        f"> {escape_markdown(CHAIN_SENTENCE)}",
        "",
    ]
    if not records:
        lines += ["Bu disa aktarimda kayit yok.", ""]
    for index, view in enumerate(records, start=1):
        lines += _markdown_record(view, index)

    payload = "\n".join(lines).encode("utf-8")
    assert_no_forbidden_claim(payload.decode("utf-8"), where="markdown export")
    return payload


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
    "ExportConsent",
    "ExportFormat",
    "ExportRefusedError",
    "build_export",
    "build_json_export",
    "build_markdown_export",
    "escape_markdown",
]
