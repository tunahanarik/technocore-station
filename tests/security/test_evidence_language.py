"""Which text is a claim, which text is data, and what each one may do.

The forbidden-phrase rule had a hole in it that no test could see, because no
test ever tried to violate it. Turning ``assert_no_forbidden_claim`` into a
no-op left the whole suite green: every existing assertion checked that this
product's own strings were clean, and none checked that a dirty one is
refused. A guard nothing exercises is a comment with a function call in front
of it.

Worse, the guard was pointed at the wrong text. It ran over the finished
export document, which contains a **message body** and an excerpt from a
**remote error response**. A server answering a capture with

    HTTP 429 - Rate limited. Bu yanit bir sunucu kaniti sayilmaz.

put those words into ``capture_detail``, and from there into both export
formats, and from there into a ``ForbiddenClaimError`` on every export of the
whole archive, for good - a ``ValueError`` that no handler caught, so a 500
rather than a refusal, with no delete route to recover from it. A remote
server could decide that a user's archive may never leave their machine.

So the two directions are tested apart:

* **a claim** - a sentence this product writes - is refused, and the refusal
  is a clean 400-shaped error rather than a crash;
* **data** - a remote excerpt, a user's own message - is neutralised where it
  joins one of our sentences, is kept where it is quoted as itself, and never
  refuses anything.
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import Engine
from station_api.evidence import export as export_module
from station_api.evidence.audit import AuditChain, AuditEventName
from station_api.evidence.audit_envelope import AuditEnvelope
from station_api.evidence.export import (
    EXPORT_FORMATS,
    PRODUCT_SENTENCES,
    ExportConsent,
    build_export,
    build_json_export,
    escape_markdown,
)
from station_api.evidence.language import (
    FORBIDDEN_PHRASES,
    NEUTRALISED_MARK,
    ForbiddenClaimError,
    _fold_spans,
    assert_no_forbidden_claim,
    find_forbidden_phrases,
    fold,
    neutralise_forbidden_claims,
)
from station_api.evidence.service import EvidenceError
from station_api.evidence.states import CaptureState

from tests.security.compose_fixtures import TEST_ROOM, build_harness
from tests.security.evidence_fixtures import build_evidence, export_transport

pytestmark = pytest.mark.security

MARKERS = frozenset({"p", "mb", "d", "e"})

FIXED_TIME = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def _consent() -> ExportConsent:
    return ExportConsent.granted(acknowledged=True, now=FIXED_TIME)

#: A remote error body that says one of the forbidden things. Turkish
#: spelling on purpose: the registry is folded, and a check that caught only
#: the ASCII spelling would be one anybody could pass by accident.
HOSTILE_ERROR_BODY = (
    "Rate limited. Bu yanit bir sunucu kanıtı sayilmaz, tekrar deneyin."
)

#: A message a user might legitimately write. It contains a forbidden phrase
#: and is not a claim by this product - it is the user's own sentence about
#: this product, which is exactly the text an archive exists to keep.
USER_TEXT_WITH_PHRASE = "Bunu sakin sunucu kanıtı diye anlatma."


# ---------------------------------------------------------------------------
# Data: imported text may never refuse a file
# ---------------------------------------------------------------------------


def _record_one(service: object, engine: Engine) -> str:
    harness = build_harness(engine, evidence=service)
    draft = harness.service.draft(  # type: ignore[attr-defined]
        session_id=harness.session_id, room=TEST_ROOM, text="TEST-ONLY mesaj"  # type: ignore[attr-defined]
    )
    signed = harness.service.sign(  # type: ignore[attr-defined]
        session_id=harness.session_id,  # type: ignore[attr-defined]
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    result = harness.service.send(  # type: ignore[attr-defined]
        session_id=harness.session_id, send_token=signed.send_token  # type: ignore[attr-defined]
    )
    return str(result.evidence_id)


def test_a_hostile_remote_error_body_cannot_lock_the_archive(
    engine: Engine, data_dir: Path
) -> None:
    """The failure this whole split exists to prevent, end to end.

    One capture against a server that answers 429 with a forbidden phrase in
    the body. Before the fix this produced a record whose ``capture_detail``
    carried the phrase, which made **both** export formats raise on **every**
    attempt, permanently, as an uncaught ``ValueError``.
    """
    service = build_evidence(
        engine,
        data_dir,
        transport=export_transport(HOSTILE_ERROR_BODY.encode("utf-8"), status=429),
    )
    evidence_id = _record_one(service, engine)

    capture = service.capture(evidence_id=evidence_id, markers=MARKERS)
    assert capture.state is CaptureState.FETCH_FAILED
    assert "429" in capture.detail, "the failure is still explained"

    # The phrase is gone from the sentence we wrote, and its removal is
    # visible rather than silent.
    assert find_forbidden_phrases(capture.detail) == ()
    assert NEUTRALISED_MARK in capture.detail

    # Every surface a person keeps still works, twice, in both formats.
    for _attempt in range(2):
        for export_format in EXPORT_FORMATS:
            payload = service.export(
                export_format=export_format, consent=_consent()
            ).payload
            assert payload

    # And the record itself is unchanged and re-capturable.
    stored = service.get(evidence_id)
    assert find_forbidden_phrases(stored.capture_detail) == ()
    again = service.capture(evidence_id=evidence_id, markers=MARKERS)
    assert again.state is CaptureState.FETCH_FAILED


def test_a_users_own_message_is_archived_verbatim_and_exports_fine(
    engine: Engine, data_dir: Path
) -> None:
    """A message is data. It is kept as written and it refuses nothing.

    Scanning the finished document meant a user could lock their own archive
    by typing a sentence about this product into a message - which is not a
    rule against over-claiming, it is a rule against writing.
    """
    service = build_evidence(engine, data_dir)
    harness = build_harness(engine, evidence=service)
    draft = harness.service.draft(
        session_id=harness.session_id, room=TEST_ROOM, text=USER_TEXT_WITH_PHRASE
    )
    signed = harness.service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    harness.service.send(session_id=harness.session_id, send_token=signed.send_token)

    records = service.list_records()
    assert USER_TEXT_WITH_PHRASE in records[0].canonical, "kept exactly as written"

    for export_format in EXPORT_FORMATS:
        payload = build_export(
            records, export_format=export_format, consent=_consent()
        ).decode("utf-8")
        # The user's words are in the file. They are the archive.
        assert find_forbidden_phrases(payload) != (), (
            "the message really does carry the phrase, so this test is about "
            "something"
        )
        assert "sunucu" in payload


# ---------------------------------------------------------------------------
# Claims: our own wording is refused, cleanly
# ---------------------------------------------------------------------------


def test_a_forbidden_phrase_in_our_own_export_wording_refuses_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mutation control for the export half of the guard.

    With ``assert_no_forbidden_claim`` turned into a no-op this test fails and
    the suite is red - which is what was missing before, when the same
    mutation left all 156 tests green.
    """
    monkeypatch.setattr(
        export_module,
        "PRODUCT_SENTENCES",
        (*PRODUCT_SENTENCES, "Bu kayit bir sunucu kanitidir."),
    )

    for export_format in EXPORT_FORMATS:
        with pytest.raises(ForbiddenClaimError):
            build_export([], export_format=export_format, consent=_consent())


def test_our_own_over_claim_is_a_refusal_and_not_a_five_hundred(
    engine: Engine, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``ForbiddenClaimError`` is a ``ValueError``, so it has to be caught.

    Uncaught, it reached the route as an unhandled exception and the user as a
    500. It cannot be raised by anything a user or a server supplies any more,
    but a bug in our own wording is still a refusal to state plainly.
    """
    service = build_evidence(engine, data_dir)
    monkeypatch.setattr(
        export_module,
        "PRODUCT_SENTENCES",
        (*PRODUCT_SENTENCES, "degismez kayit"),
    )

    with pytest.raises(EvidenceError):
        service.export(export_format="json", consent=_consent())


def test_an_audit_detail_carrying_a_forbidden_claim_refuses_the_link(
    engine: Engine, data_dir: Path
) -> None:
    """The audit half of the guard, which no test exercised either.

    An audit detail is assembled from fixed words, a room name and a state
    name - all of them ours - so this is the wording check doing its real job.
    """
    chain = AuditChain(engine, AuditEnvelope(data_dir))
    chain.ensure_ready()

    with pytest.raises(ForbiddenClaimError):
        chain.record(
            event=AuditEventName.CHAIN_STARTED,
            subject="test-only",
            detail="Bu zincir degistirilemez kayit uretir.",
        )


def test_every_sentence_this_product_writes_into_an_export_is_checked() -> None:
    """The registry is not empty and covers what the writers actually say."""
    assert len(PRODUCT_SENTENCES) >= 10
    for sentence in PRODUCT_SENTENCES:
        assert find_forbidden_phrases(sentence) == (), sentence
    # A file built from a clean registry is built.
    assert build_json_export([], consent=_consent())


def test_no_string_literal_in_the_evidence_package_carries_a_forbidden_phrase(
    api_source_root: Path,
) -> None:
    """The static half: every literal in the package, not just the registry.

    The runtime check covers the sentences that could plausibly over-claim.
    This covers the short labels the writers interpolate as well, so a new one
    cannot arrive carrying a phrase that the registry was never told about.
    """
    package = api_source_root / "station_api" / "evidence"
    offenders: list[str] = []

    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if path.name == "language.py":
                continue  # the registry itself, which is written out in full
            found = find_forbidden_phrases(node.value)
            if found:
                offenders.append(f"{path.name}:{node.lineno} {found}")

    assert offenders == [], f"forbidden phrases in source strings: {offenders}"


# ---------------------------------------------------------------------------
# Neutralisation itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phrase", FORBIDDEN_PHRASES)
def test_every_registered_phrase_is_neutralised_in_both_spellings(
    phrase: str,
) -> None:
    """Folded matching, applied to removal and not only to detection."""
    for spelling in (phrase, phrase.upper(), phrase.replace("i", "ı")):
        text = f"once {spelling} sonra"
        assert find_forbidden_phrases(text) != ()
        cleaned = neutralise_forbidden_claims(text)
        assert find_forbidden_phrases(cleaned) == ()
        assert cleaned.startswith("once ")
        assert cleaned.endswith(" sonra"), "the surrounding text survives"
        assert NEUTRALISED_MARK in cleaned


def test_clean_text_comes_back_unchanged() -> None:
    """Neutralisation is not a rewrite of every string that passes through."""
    for text in ("", "sunucu gozlemi", "yerel arsiv kaydi", "429 Too Many"):
        assert neutralise_forbidden_claims(text) == text


def test_the_span_tracking_fold_agrees_with_the_folded_string() -> None:
    """Two implementations of one normalisation, pinned against each other.

    Replacement uses the span-tracking fold; detection uses the vectorised
    one. If they drifted, the precise pass could leave a phrase standing - so
    they are compared here, and ``neutralise_forbidden_claims`` re-checks its
    own output at runtime as well.
    """
    samples = (
        "Sunucu Kanıtı",
        "SUNUCU  KANITI",
        "degismez\tkayit",
        "İmza\r\nkaniti",
        "ﬁnal degistirilemez kayit",
        "",
    )
    for sample in samples:
        folded, spans = _fold_spans(sample)
        assert folded == fold(sample), sample
        assert len(spans) == len(folded)


def test_a_neutralised_excerpt_never_removes_more_than_the_phrase() -> None:
    text = "Sunucu 429 dondu: bu bir sunucu kaniti degildir, tekrar deneyin."
    cleaned = neutralise_forbidden_claims(text)

    assert cleaned.startswith("Sunucu 429 dondu: bu bir ")
    assert cleaned.endswith(" degildir, tekrar deneyin.")
    assert find_forbidden_phrases(cleaned) == ()


# ---------------------------------------------------------------------------
# Nothing is silently dropped (the other half of SI-194)
# ---------------------------------------------------------------------------


def test_the_markdown_escaper_substitutes_and_never_deletes() -> None:
    """Invisible characters become a space; nothing is removed or truncated.

    The claim used to be that nothing is silently dropped, while the escaper
    ran everything through ``safe_display`` - which truncates at two hundred
    characters and strips the ends. A message longer than that came out of the
    export shorter than it went in, with an ellipsis nobody could tell from
    the user's own.
    """
    # A newline, a zero-width non-joiner, an RTL override and a NUL.
    swept = "a\nb\u200cc\u202ed\x00e"
    escaped = escape_markdown(swept)

    assert escaped == "a b c d e", "each invisible character became one space"
    assert len(escaped) == len(swept), "one character in, one character out"

    long_value = "k" * 5000
    assert escape_markdown(long_value) == long_value, "no truncation"

    # And the visible text of an ordinary value survives the escaper exactly.
    plain = "kanit | tablo (1) #baslik"
    assert escape_markdown(plain).replace("\\", "") == plain


def test_assert_no_forbidden_claim_names_what_it_found() -> None:
    with pytest.raises(ForbiddenClaimError) as raised:
        assert_no_forbidden_claim("bir degismez kayit", where="test")
    assert "degismez kayit" in str(raised.value)
    assert "test" in str(raised.value)
