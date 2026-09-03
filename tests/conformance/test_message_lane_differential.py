"""The composed message lane, differentially against the pinned signer.

``test_signature_differential.py`` proves the *engine* agrees with the
reference for a hand-written table of (room, nonce, text) triples. This file
asks a narrower and, for Package D, more useful question: does the message the
**composer** actually assembles - a swept text, a reserved nonce and a
resolved room, walked through the real approval chain - still produce the
signature the reference produces for those same three values?

The distinction matters because everything between the user's keystrokes and
the request body is Station's own code. The sweep could be applied twice, the
nonce could be normalised through an ``int``, the room could be lower-cased
somewhere, the body could carry the raw text instead of the swept text. Each
of those would leave the engine correct and the product wrong, and the
reference signer is the only witness that cannot be fooled by our own
misunderstanding.

The oracle is ``vendor/technocore-reference/scripts/sign.py``, invoked as a
subprocess, with its vendored files' SHA-256 verified first. Nothing here
contacts Technocore; the write client is a mock transport and the lobby is
never a target (INV-05).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Engine
from technocore_conform import MESSAGE_POLICY, canonical_message, sweep

from tests.conformance.oracle import official_message_signature
from tests.security.compose_fixtures import (
    TEST_ONLY_SEED,
    TEST_ROOM,
    TEST_ROOM_ALT,
    ComposeHarness,
    build_harness,
)

pytestmark = pytest.mark.conformance

#: The TEST-ONLY seed the composer harness signs with, in the hex form the
#: reference signer takes on its command line. Derived from the same constant
#: rather than pasted, so the two can never drift apart.
TEST_ONLY_SEED_HEX = TEST_ONLY_SEED.hex()

#: Raw inputs chosen for what they do to the *composer*, not to the engine.
#: Each one is text a user could type that the sweep changes, so the swept
#: form and the typed form differ - which is exactly when signing the wrong
#: one stays invisible until the server refuses it.
COMPOSED_CASES = [
    pytest.param("hello world", id="plain"),
    pytest.param("   bosluklar kirpilir   ", id="trimmed"),
    pytest.param("İstanbul'dan selam, ĞÜŞİÖÇ ğüşiöç", id="turkish"),
    pytest.param("satir\nsonu\tvar", id="control-characters"),
    pytest.param("trojan ‮ source ‬", id="bidi-override"),
    pytest.param("gizli\U000e0041\U000e0042talimat", id="unicode-tags"),
    pytest.param("sifir​genislik", id="zero-width"),
    pytest.param("pipe|icinde|metin", id="separator-in-text"),
    pytest.param("aile \U0001f468‍\U0001f469‍\U0001f467 burada", id="emoji-zwj"),
    pytest.param("a" * 4096, id="at-the-limit"),
]


def _sign_through_the_composer(
    harness: ComposeHarness, *, room: str, text: str
) -> tuple[str, str, str]:
    """Walk draft -> sign and return ``(nonce, canonical, signature)``."""
    draft = harness.service.draft(
        session_id=harness.session_id, room=room, text=text
    )
    signed = harness.service.sign(
        session_id=harness.session_id,
        draft_id=draft.draft_id,
        confirmed_digest=draft.draft_digest,
        vault_passphrase=None,
    )
    return signed.nonce, signed.canonical, signed.signature


@pytest.mark.parametrize("text", COMPOSED_CASES)
def test_the_composed_signature_equals_the_reference_signature(
    engine: Engine, vendor_root: Path, text: str
) -> None:
    """The whole chain agrees with the pinned signer, character for character.

    Ed25519 is deterministic, so this is a real equality rather than "both
    produced something valid". The reference is given the **swept** text,
    because that is what the server stores and therefore what the signature
    must cover; handing it the raw text is the mistake this test would catch.
    """
    harness = build_harness(engine)
    nonce, canonical, signature = _sign_through_the_composer(
        harness, room=TEST_ROOM, text=text
    )
    swept = sweep(text, MESSAGE_POLICY)

    official_did, official_signature = official_message_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_HEX,
        room=TEST_ROOM,
        nonce=nonce,
        text=swept,
    )

    assert signature == official_signature
    assert canonical == f"{TEST_ROOM}|{nonce}|{swept}"
    assert harness.identity.did == official_did


def test_the_request_body_carries_the_bytes_the_reference_signed(
    engine: Engine, vendor_root: Path
) -> None:
    """The last hop: what leaves the process, against the oracle.

    Everything up to here could be right and the body could still carry the
    raw text, a re-swept text or a re-derived nonce. This compares the actual
    JSON that went out with the signature the reference produces over the
    fields inside it.
    """
    raw = "  taslak​metni  "
    harness = build_harness(engine)
    nonce, _, signature = _sign_through_the_composer(
        harness, room=TEST_ROOM, text=raw
    )
    token = harness.service._approvals
    pending = next(iter(token._tokens))
    harness.service.send(session_id=harness.session_id, send_token=pending)

    body = json.loads(harness.writes.requests[0].content)
    official_did, official_signature = official_message_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_HEX,
        room=TEST_ROOM,
        nonce=body["nonce"],
        text=body["text"],
    )

    assert body["sig"] == official_signature == signature
    assert body["did"] == official_did
    assert body["nonce"] == nonce
    assert body["text"] == sweep(raw, MESSAGE_POLICY)


def test_the_reserved_nonce_is_signed_as_the_exact_characters_sent(
    engine: Engine, vendor_root: Path
) -> None:
    """A nonce that survived an ``int`` round trip would break here.

    ``"007"`` and ``"7"`` are one number and two different signatures. The
    reserver never produces a leading zero, so the risk is the opposite
    direction: a value re-derived from the integer somewhere in the chain
    would still match today and would stop matching the moment anything
    formatted it differently. Signing the reference with the *string* the
    body carries is what pins that.
    """
    harness = build_harness(engine)
    nonce, canonical, signature = _sign_through_the_composer(
        harness, room=TEST_ROOM, text="nonce baytlari"
    )

    assert nonce == str(int(nonce)), "the reserved nonce is not in minimal form"

    _, official_signature = official_message_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_HEX,
        room=TEST_ROOM,
        nonce=nonce,
        text="nonce baytlari",
    )
    assert signature == official_signature
    assert canonical.split("|")[1] == nonce


def test_a_room_class_prefix_is_signed_verbatim(
    engine: Engine, vendor_root: Path
) -> None:
    """``mb-`` and ``e-`` are part of the room name, not decoration.

    The composer parses class markers off the name to decide what to tell the
    user. A parse that also *consumed* them would sign a different room than
    the one the request addresses.
    """
    harness = build_harness(engine)
    room = "mb-p-station-test-only"
    nonce, canonical, signature = _sign_through_the_composer(
        harness, room=room, text="sinif onekleri korunur"
    )

    _, official_signature = official_message_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_HEX,
        room=room,
        nonce=nonce,
        text="sinif onekleri korunur",
    )

    assert signature == official_signature
    assert canonical.startswith(f"{room}|")


def test_the_oracle_comparison_is_sensitive_to_every_signed_field(
    engine: Engine, vendor_root: Path
) -> None:
    """The negative control, so the equalities above mean something.

    A comparison that matched whatever it was given would pass every test in
    this file while proving nothing. Each structural field is perturbed in
    turn and the reference must produce a *different* signature.

    Raw-versus-swept is deliberately not one of the perturbations: the
    reference signer applies its own ``clean_text`` to whatever it is handed,
    so the oracle cannot tell the two apart and an assertion that it could
    would be false. That property is pinned where it can be - the sweep
    differential, and the body assertion above that what leaves the process
    carries the swept text rather than the typed text.
    """
    text = "duyarlilik kontrolu"
    harness = build_harness(engine)
    nonce, _, signature = _sign_through_the_composer(
        harness, room=TEST_ROOM, text=text
    )

    _, same = official_message_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_HEX,
        room=TEST_ROOM,
        nonce=nonce,
        text=text,
    )
    assert signature == same

    perturbations = [
        (TEST_ROOM_ALT, nonce, text),
        (TEST_ROOM, str(int(nonce) + 1), text),
        (TEST_ROOM, nonce, text + "."),
    ]
    for room, other_nonce, other_text in perturbations:
        _, different = official_message_signature(
            vendor_root,
            seed_hex=TEST_ONLY_SEED_HEX,
            room=room,
            nonce=other_nonce,
            text=other_text,
        )
        assert signature != different, (
            f"changing ({room}, {other_nonce}, {other_text!r}) produced the "
            "same signature, so the comparison proves nothing"
        )


def test_the_canonical_payload_the_signer_saw_is_the_one_that_was_sent(
    engine: Engine,
) -> None:
    """No second sweep, no rebuild, no drift between signing and sending.

    Needs no oracle: it compares the payload object handed to the signer with
    a payload rebuilt from the request body, which is the same comparison the
    server makes against its stored bytes.
    """
    harness = build_harness(engine)
    _sign_through_the_composer(harness, room=TEST_ROOM, text="  iki kere supurulmez  ")

    store = harness.service._approvals
    pending = next(iter(store._tokens))
    harness.service.send(session_id=harness.session_id, send_token=pending)

    signed_payload = harness.signer.signed[0]
    body = json.loads(harness.writes.requests[0].content)
    rebuilt = canonical_message(
        room=TEST_ROOM, nonce=body["nonce"], text=body["text"]
    )

    assert rebuilt.canonical_bytes == signed_payload.canonical_bytes
