"""Export: consent, determinism, injection and the download name.

Four things are being defended.

**Consent.** There is no spelling of "export anyway" that both type-checks and
runs. The service takes an ``ExportConsent``, the consent object is
constructible only through a classmethod that takes ``Literal[True]``, and the
route's request model has no default for the flag.

**Determinism.** The same records give the same bytes. A user who exports
twice and diffs should see nothing, so that a difference means something.

**Injection.** ``safe_display`` sweeps control, format and bidi characters and
escapes no markup at all. A message body is user and network text; in a
Markdown file it can open a link, a raw ``<img>``, a table row or a fence.
Every interpolated value therefore goes through a Markdown escaper.

**The download name.** The header used to be a raw f-string whose only
variable was a base58 DID tail. Package E puts caller-influenced text in a
download name, so the name is rebuilt from an allow-list.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import Engine
from station_api.downloads import (
    MAX_STEM_CHARS,
    content_disposition,
    safe_download_filename,
    safe_filename_stem,
    split_suffix,
)
from station_api.evidence.export import (
    CHAIN_SENTENCE,
    EXPORT_FORMATS,
    MARKDOWN_SCOPE_NOTE,
    ExportConsent,
    ExportRefusedError,
    build_export,
    build_json_export,
    build_markdown_export,
    escape_markdown,
)
from station_api.evidence.language import find_forbidden_phrases
from station_api.evidence.records import LEVEL_NAMES
from station_api.evidence.service import EvidenceError
from station_api.strict_json import b64u_decode, loads_strict

from tests.security.compose_fixtures import TEST_ROOM, build_harness
from tests.security.evidence_fixtures import build_evidence

pytestmark = pytest.mark.security

FIXED_TIME = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)

#: A message body carrying every markup weapon a Markdown file has.
DANGEROUS_TEXT = (
    "[tikla](javascript:alert(1)) <img src=x onerror=alert(1)> "
    "`kod` | tablo | satiri ### baslik"
)


def _consent() -> ExportConsent:
    return ExportConsent.granted(acknowledged=True, now=FIXED_TIME)


def _service_with_records(
    engine: Engine, data_dir: Path, *, text_body: str = "TEST-ONLY mesaj"
) -> object:
    service = build_evidence(engine, data_dir)
    harness = build_harness(engine, evidence=service)
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=text_body
    )
    signed = harness.service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    harness.service.send(session_id=harness.session_id, send_token=signed.send_token)
    return service


# ---------------------------------------------------------------------------
# Consent
# ---------------------------------------------------------------------------


def test_an_export_without_consent_is_unrepresentable_and_refused() -> None:
    """Two independent refusals, because this one is worth two."""
    with pytest.raises(ExportRefusedError):
        ExportConsent.granted(acknowledged=False, now=FIXED_TIME)  # type: ignore[arg-type]

    forged = ExportConsent(acknowledged=False, requested_at=FIXED_TIME)
    with pytest.raises(ExportRefusedError):
        build_json_export([], consent=forged)
    with pytest.raises(ExportRefusedError):
        build_markdown_export([], consent=forged)


def test_the_service_refuses_an_export_without_consent(
    engine: Engine, data_dir: Path
) -> None:
    service = build_evidence(engine, data_dir)
    with pytest.raises(EvidenceError):
        service.export(
            export_format="json",
            consent=ExportConsent(acknowledged=False, requested_at=FIXED_TIME),
        )


def test_the_export_request_model_has_no_default_acknowledgement() -> None:
    """A body that omits the flag is a 422 before any handler runs."""
    from station_api.schemas import EvidenceExportRequest

    field = EvidenceExportRequest.model_fields["acknowledged"]
    assert field.is_required(), "consent must not have a default"

    with pytest.raises(ValidationError):
        EvidenceExportRequest(format="json")  # type: ignore[call-arg]


def test_an_export_is_itself_an_audit_event(engine: Engine, data_dir: Path) -> None:
    """A copy of the archive leaving the machine is worth remembering."""
    service = build_evidence(engine, data_dir)
    before = service.verify_chain().link_count

    service.export(export_format="json", consent=_consent())

    after = service.verify_chain()
    assert after.link_count == before + 1
    assert after.is_intact


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_the_same_records_produce_the_same_bytes(
    engine: Engine, data_dir: Path
) -> None:
    service = _service_with_records(engine, data_dir)
    records = service.list_records()  # type: ignore[attr-defined]

    for export_format in EXPORT_FORMATS:
        first = build_export(
            records, export_format=export_format, consent=_consent()
        )
        second = build_export(
            records, export_format=export_format, consent=_consent()
        )
        assert first == second
        assert first, "an export of a real record is not empty"


def test_the_json_export_is_canonical_json(engine: Engine, data_dir: Path) -> None:
    """Sorted keys, no whitespace - the encoding a vector already pins."""
    service = _service_with_records(engine, data_dir)
    payload = build_json_export(
        service.list_records(), consent=_consent()  # type: ignore[attr-defined]
    )

    document = loads_strict(payload)
    assert document["kind"] == "technocore-station.evidence-export"
    assert b'", "' not in payload, "canonical JSON carries no separator whitespace"


def test_every_level_is_named_and_level_four_is_null(
    engine: Engine, data_dir: Path
) -> None:
    """An empty level is written as empty, never omitted or guessed."""
    service = _service_with_records(engine, data_dir)
    document = loads_strict(
        build_json_export(service.list_records(), consent=_consent())  # type: ignore[attr-defined]
    )

    levels = document["records"][0]["levels"]
    assert set(levels) == {
        "1_imza_kaniti",
        "2_sunucu_gozlemi",
        "3_yerel_kayit_zamani",
        "4_harici_anchor",
    }
    assert levels["4_harici_anchor"]["value"] is None
    assert levels["4_harici_anchor"]["present"] is False
    assert levels["2_sunucu_gozlemi"]["present"] is False, "no capture was run"


def test_the_exported_request_bytes_round_trip_exactly(
    engine: Engine, data_dir: Path
) -> None:
    """base64url, decoded back to the bytes that were sent."""
    service = _service_with_records(engine, data_dir)
    view = service.list_records()[0]  # type: ignore[attr-defined]
    document = loads_strict(
        build_json_export([view], consent=_consent())  # type: ignore[arg-type]
    )

    encoded = document["records"][0]["levels"]["2_sunucu_gozlemi"]["request_b64url"]
    assert b64u_decode(encoded) == view.request_body
    assert set(json.loads(view.request_body)) == {"did", "sig", "nonce", "text"}


def test_two_exports_taken_at_different_times_are_byte_identical(
    engine: Engine, data_dir: Path
) -> None:
    """The determinism claim, with the clock actually moving between them.

    ``test_the_same_records_produce_the_same_bytes`` above used one fixed
    consent time for both calls, so it could not see the ``exported_at`` stamp
    that made every real pair of exports differ. The stamp is in a response
    header now, and this test uses two different times on purpose.
    """
    service = _service_with_records(engine, data_dir)
    records = service.list_records()  # type: ignore[attr-defined]
    early = ExportConsent.granted(acknowledged=True, now=FIXED_TIME)
    later = ExportConsent.granted(
        acknowledged=True, now=datetime(2027, 1, 1, 3, 4, 5, tzinfo=UTC)
    )

    for export_format in EXPORT_FORMATS:
        first = build_export(records, export_format=export_format, consent=early)
        second = build_export(records, export_format=export_format, consent=later)
        assert first == second, export_format
        # Neither consent time is in the file. Asserted on the full instant
        # rather than on the date: the record's own ``recorded_at`` is in
        # there and is legitimately today's date.
        for consent in (early, later):
            assert consent.requested_at.isoformat().encode() not in first


def test_the_service_returns_the_export_time_beside_the_bytes(
    engine: Engine, data_dir: Path
) -> None:
    """Removed from the document, not lost: the route puts it in a header."""
    service = build_evidence(engine, data_dir)
    result = service.export(export_format="json", consent=_consent())

    assert result.exported_at == FIXED_TIME
    assert b"exported_at" not in result.payload


def test_both_formats_carry_the_canonical_string_a_signature_covers(
    engine: Engine, data_dir: Path
) -> None:
    """The scope difference between the two formats, resolved and stated.

    JSON carried the canonical string as plain text and Markdown carried only
    its SHA-256, which made the Markdown export a summary nobody could check
    anything against - a hash verifies a string you already have. The text is
    now in both. The raw **bytes** stay in JSON alone, and the Markdown file
    says so in its own header rather than leaving a reader to notice.
    """
    service = _service_with_records(engine, data_dir)
    records = service.list_records()  # type: ignore[attr-defined]
    canonical = records[0].canonical
    assert canonical, "the fixture really produced a canonical string"

    document = loads_strict(build_json_export(records, consent=_consent()))
    assert document["records"][0]["levels"]["1_imza_kaniti"]["canonical"] == canonical

    markdown = build_markdown_export(records, consent=_consent()).decode("utf-8")
    assert escape_markdown(canonical) in markdown
    assert escape_markdown(MARKDOWN_SCOPE_NOTE) in markdown
    # The bytes are still JSON-only, which is the part that is documented
    # rather than equalised.
    for key in ("captured_line_b64url", "request_b64url", "response_b64url"):
        assert key in str(document["records"][0]["levels"]["2_sunucu_gozlemi"])
    assert "b64url" not in markdown


def test_an_empty_archive_still_exports_a_well_formed_file() -> None:
    assert loads_strict(build_json_export([], consent=_consent()))["record_count"] == 0
    assert b"kayit yok" in build_markdown_export([], consent=_consent())


# ---------------------------------------------------------------------------
# Injection
# ---------------------------------------------------------------------------


def test_the_markdown_escaper_neutralises_every_markup_weapon() -> None:
    """Every metacharacter carries a backslash, with none left bare.

    Asserted positionally rather than by substring: ``"<img" not in escaped``
    would be satisfied by ``\\<img``, which is correct, and equally satisfied
    by an escaper that deleted the ``<`` instead of escaping it, which would
    be a silently lossy export.
    """
    escaped = escape_markdown(DANGEROUS_TEXT)

    specials = set("\\`*_{}[]()#+-.!|<>&~")
    for index, char in enumerate(escaped):
        if char in specials and char != "\\":
            assert index > 0 and escaped[index - 1] == "\\", (
                f"{char!r} at {index} is not escaped: {escaped!r}"
            )

    # And nothing was dropped: the visible text is still all there.
    assert escaped.replace("\\", "") == DANGEROUS_TEXT
    assert "\\[tikla\\]\\(javascript:" in escaped
    assert "\\<img" in escaped


def test_dangerous_imported_text_is_inert_in_the_markdown_export(
    engine: Engine, data_dir: Path
) -> None:
    """The end-to-end version: a real send whose text is an attack.

    ``safe_display`` alone would have let all of this through: it removes
    control and bidi characters and escapes no markup whatsoever.

    The assertions are made against the document with every backslash-escaped
    pair removed, rather than as plain substring checks. ``"<img" not in
    payload`` was satisfied by an escaper that deleted the ``<`` **and** by one
    that escaped it, and it was also satisfied by this document not containing
    the message at all - which is what it was really testing until the
    canonical string was added to this format.
    """
    service = _service_with_records(engine, data_dir, text_body=DANGEROUS_TEXT)
    payload = build_markdown_export(
        service.list_records(), consent=_consent()  # type: ignore[attr-defined]
    ).decode("utf-8")

    # The message really is in this file, so the assertions below are about
    # something. It is there in exactly its inert form.
    assert escape_markdown(DANGEROUS_TEXT) in payload

    bare = re.sub(r"\\(.)", "", payload)
    # Not one unescaped angle bracket, square bracket, parenthesis or backtick
    # survives out of the message: the tag never opens, the link never forms.
    assert "<img" not in bare
    assert "](javascript:" not in bare
    assert "`kod`" not in bare
    # ``onerror=alert(1)`` is still *present* - it is inert because the tag
    # around it never opens, not because anything was deleted. An export that
    # dropped it would be an archive of a message the user did not send.
    assert "onerror=alert(1)" in payload.replace("\\", "")


def test_a_bidi_override_cannot_reach_the_export() -> None:
    """``safe_display`` still does its half: control and format characters."""
    escaped = escape_markdown("dosya‮gnp.exe")
    assert "‮" not in escaped


def test_no_export_can_carry_a_forbidden_phrase(
    engine: Engine, data_dir: Path
) -> None:
    """The backend half of a rule that was only enforced on the frontend."""
    service = _service_with_records(engine, data_dir)
    records = service.list_records()  # type: ignore[attr-defined]

    for export_format in EXPORT_FORMATS:
        payload = build_export(
            records, export_format=export_format, consent=_consent()
        ).decode("utf-8")
        assert find_forbidden_phrases(payload) == ()

    assert find_forbidden_phrases(CHAIN_SENTENCE) == ()
    assert "tespit edici" in CHAIN_SENTENCE
    for name in LEVEL_NAMES:
        assert find_forbidden_phrases(name) == ()


# ---------------------------------------------------------------------------
# The download name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hostile",
    [
        'kanit"; filename="evil.exe',
        "kanit\r\nSet-Cookie: a=b",
        "kanit; charset=utf-8",
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "kanit‮gnp.exe",
        "kanıt-türkçe",
        "kanit\x00null",
        "",
        "...",
        "-",
    ],
)
def test_the_filename_sanitiser_removes_every_header_weapon(hostile: str) -> None:
    """Rebuilt from an allow-list rather than filtered.

    A deny-list is a list of the attacks someone thought of, and this is a
    header where being unimaginative is free.
    """
    name = safe_download_filename(hostile, suffix=".json")
    header = content_disposition(name)

    assert name.endswith(".json")
    assert name.isascii()
    for forbidden in ('"', "\r", "\n", ";", "/", "\\", "‮", "\x00", ".."):
        assert forbidden not in name, f"{forbidden!r} survived in {name!r}"
    assert header == f'attachment; filename="{name}"'
    assert header.count('"') == 2


def test_the_header_keeps_the_extension_on_a_long_name() -> None:
    """The safety net was eating the thing it was protecting.

    ``content_disposition`` re-sanitised the complete name as though it were a
    stem, so ``MAX_STEM_CHARS`` cut a three-hundred-character name at eighty -
    taking ``.json`` off the end. Only ``safe_download_filename`` was under
    test; the function whose output goes on the wire was not.
    """
    for suffix in (".json", ".md", ".tcrec"):
        long_name = safe_download_filename("a" * 300, suffix=suffix)
        header = content_disposition(long_name)

        assert header.endswith(f'{suffix}"'), header
        assert header.count('"') == 2
        assert len(header) < 200


def test_the_header_is_idempotent_over_an_already_safe_name() -> None:
    """Sanitising twice must not change a name the caller already cleaned."""
    for stem, suffix in (
        ("technocore-station-kanit", ".json"),
        ("technocore-station-z6MkTESTONLY", ".tcrec"),
        ("a.b.c", ".md"),
    ):
        name = safe_download_filename(stem, suffix=suffix)
        assert content_disposition(name) == f'attachment; filename="{name}"'


def test_a_dot_that_is_not_an_extension_stays_part_of_the_stem() -> None:
    """A long trailing run after a dot is a name, not a file type."""
    stem, suffix = split_suffix("kanit." + "z" * 40)
    assert suffix == ""
    assert stem == "kanit." + "z" * 40

    assert split_suffix("kanit.json") == ("kanit", ".json")
    assert split_suffix("kanit") == ("kanit", "")


@pytest.mark.parametrize(
    "reserved",
    ["CON", "con", "NUL", "nul.json", "AUX", "PRN", "COM1", "lpt9", "Com4.md"],
)
def test_a_windows_device_name_is_not_handed_to_the_browser(reserved: str) -> None:
    """``CON.json`` does not name a file on Windows; it names a device.

    The allow-list rebuilt the name out of safe characters and then handed
    back one that the operating system refuses to open, which is a confusing
    failure in a save dialog rather than a dangerous one - and free to remove.
    """
    stem = safe_filename_stem(reserved)
    assert stem.split(".")[0].lower() not in {
        "con",
        "prn",
        "aux",
        "nul",
        "com1",
        "com4",
        "lpt9",
    }
    assert reserved.split(".")[0].lower() in stem.lower(), "still recognisable"

    name = safe_download_filename(reserved, suffix=".json")
    assert name.endswith(".json")
    assert content_disposition(name) == f'attachment; filename="{name}"'


def test_a_name_that_sanitises_to_nothing_falls_back() -> None:
    assert safe_filename_stem("///") == "indirme"
    assert safe_filename_stem("...", fallback="kanit") == "kanit"


def test_the_stem_is_bounded_so_the_suffix_always_survives() -> None:
    name = safe_download_filename("k" * 500, suffix=".md")
    assert len(name) <= MAX_STEM_CHARS + len(".md")
    assert name.endswith(".md")


def test_the_recovery_download_now_goes_through_the_same_helper(
    api_source_root: Path,
) -> None:
    """The gap ADR-0003 9 named: one raw f-string, closed.

    It was safe as written - the only variable part was a base58 DID tail -
    and that is exactly the kind of safety that stops being true when nobody
    is re-checking it.
    """
    source = (
        api_source_root / "station_api" / "routes" / "identity.py"
    ).read_text(encoding="utf-8")
    assert "content_disposition(" in source
    assert 'f\'attachment; filename="' not in source


def test_the_did_tail_still_produces_a_readable_recovery_name() -> None:
    """The sanitiser must not mangle the name it was added to protect."""
    name = safe_download_filename(
        f"technocore-station-{'z6MkTESTONLY'}", suffix=".tcrec"
    )
    assert name == "technocore-station-z6MkTESTONLY.tcrec"
