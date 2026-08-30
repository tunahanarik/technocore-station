"""AC-04 - signature encoding, and equality with the pinned reference signer.

Ed25519 is deterministic, so "the reference and we produce the same 86
characters" is a meaningful equality, not merely "both produce something
valid". The oracle is ``scripts/sign.py``, invoked as a subprocess.

Scope note: text reaches the reference signer through ``argv``, so these
cases use well-formed Unicode. Lone surrogates are covered by the in-process
sweep differential, which needs no encoding round-trip.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from technocore_conform import (
    MAX_MESSAGE_CHARS,
    MAX_NOTE_VALUE_CHARS,
    SIGNATURE_BYTES,
    SIGNATURE_CHARS,
    CanonicalPayload,
    InvalidNonceError,
    InvalidSeedError,
    MalformedSignatureError,
    SignatureMismatchError,
    canonical_message,
    canonical_note,
    decode_signature,
    did_key_from_seed,
    encode_signature,
    is_canonical_signature,
    sign_payload,
    verify_payload,
)

from tests.conformance.oracle import official_message_signature, official_note_signature

pytestmark = pytest.mark.conformance

#: TEST-ONLY seeds. Published fixtures, never operational key material.
TEST_ONLY_SEED_A = "0000000000000000000000000000000000000000000000000000000000000001"
TEST_ONLY_SEED_B = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

#: ``(room, nonce, text)`` - one case per hazard the canonical string faces.
MESSAGE_CASES = [
    ("test-room", "1", "hello world"),
    ("test-room", "42", "   trimmed both ends   "),
    ("oda-1", "1000", "İstanbul'dan selam, ĞÜŞİÖÇ ğüşiöç"),
    ("oda_2", "999", "aile \U0001f468‍\U0001f469‍\U0001f467 burada"),
    ("r", "7", "satir\nsonu\tvar"),
    ("room-with-dashes", "0", "trojan ‮ source ‬"),
    ("a1", "0000000000000000001", "pipe|icinde|metin"),
    ("z9", "9999999999999999999", "en buyuk nonce"),
    ("test-room", "007", "leading zero korunur"),
    ("a" * 48, "5", "en uzun oda adi"),
    ("tags", "3", "gizli\U000e0041\U000e0042talimat"),
    ("edge", "4", "a" * MAX_MESSAGE_CHARS),
]

#: ``(namespace, key, nonce, value)``
NOTE_CASES = [
    ("profile", "bio", "1", "kisa bir tanitim"),
    ("profil", "aciklama", "2", "Türkçe değer: ĞÜŞİÖÇ"),
    ("ns-1", "key_1", "10", "deger\nikinci satir"),
    ("ns2", "k2", "0007", "a|b|c"),
    ("profile", "tag", "88", "gizli​karakter"),
    ("edge", "big", "9", "b" * MAX_NOTE_VALUE_CHARS),
]


# --- differential against the reference signer ------------------------------


@pytest.mark.parametrize(("room", "nonce", "text"), MESSAGE_CASES)
def test_message_signature_equals_the_reference(
    vendor_root: Path, room: str, nonce: str, text: str
) -> None:
    expected_did, expected_signature = official_message_signature(
        vendor_root, seed_hex=TEST_ONLY_SEED_A, room=room, nonce=nonce, text=text
    )
    payload = canonical_message(room=room, nonce=nonce, text=text)
    produced = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_A))

    assert produced == expected_signature
    verify_payload(payload, did=expected_did, signature=expected_signature)


@pytest.mark.parametrize(("namespace", "key", "nonce", "value"), NOTE_CASES)
def test_note_signature_equals_the_reference(
    vendor_root: Path, namespace: str, key: str, nonce: str, value: str
) -> None:
    expected_did, expected_signature = official_note_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_B,
        namespace=namespace,
        key=key,
        nonce=nonce,
        value=value,
    )
    payload = canonical_note(namespace=namespace, key=key, nonce=nonce, value=value)
    produced = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_B))

    assert produced == expected_signature
    verify_payload(payload, did=expected_did, signature=expected_signature)


def test_signing_raw_text_diverges_from_the_reference(vendor_root: Path) -> None:
    """Signing what the user typed, rather than what is stored, is the classic bug.

    The server would answer 403 and only a live request would reveal it, so
    the divergence is demonstrated here in the open. Note that reaching it
    requires going around this package's API entirely: ``sign_payload`` takes
    a payload, and the only builders sweep.
    """
    room, nonce, raw = "test-room", "5", "  bosluklu  "
    seed = bytes.fromhex(TEST_ONLY_SEED_A)

    _, reference_signature = official_message_signature(
        vendor_root, seed_hex=TEST_ONLY_SEED_A, room=room, nonce=nonce, text=raw
    )
    payload = canonical_message(room=room, nonce=nonce, text=raw)

    # The swept form is what the reference signed.
    assert sign_payload(payload, seed=seed) == reference_signature

    # The raw form is not, and the two are genuinely different bytes.
    naive_canonical = f"{room}|{nonce}|{raw}".encode()
    assert naive_canonical != payload.canonical_bytes
    naive_signature = encode_signature(
        Ed25519PrivateKey.from_private_bytes(seed).sign(naive_canonical)
    )
    assert naive_signature != reference_signature


# --- AC-04: the encoding contract ------------------------------------------


def test_signature_is_86_unpadded_base64url_characters() -> None:
    payload = canonical_message(room="r", nonce="1", text="x")
    signature = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_A))

    assert len(signature) == SIGNATURE_CHARS == 86
    assert "=" not in signature
    assert "+" not in signature
    assert "/" not in signature
    assert is_canonical_signature(signature)


def test_raw_signature_is_64_bytes() -> None:
    payload = canonical_message(room="r", nonce="1", text="x")
    signature = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_A))
    assert len(decode_signature(signature)) == SIGNATURE_BYTES == 64


def test_final_character_is_always_canonical() -> None:
    """The 86th character carries four slack bits that must be zero.

    Only A, Q, g and w have that property, which is what makes the encoding
    of 64 bytes unique. Checked over many signatures, not just one.
    """
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    finals = set()
    for index in range(200):
        payload = canonical_message(room="r", nonce=str(index), text="x")
        finals.add(sign_payload(payload, seed=seed)[-1])

    assert finals <= {"A", "Q", "g", "w"}, f"non-canonical final characters: {finals}"


def test_padded_and_standard_base64_spellings_are_refused() -> None:
    payload = canonical_message(room="r", nonce="1", text="pipe-and-slash|/+")
    signature = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_A))
    raw = decode_signature(signature)

    candidates = [
        signature + "=",
        signature + "==",
        base64.b64encode(raw).decode().rstrip("="),
        signature[:-1],
        signature + "A",
        " " + signature,
        signature + " ",
        signature.replace("_", "/").replace("-", "+"),
    ]
    for bad in candidates:
        if bad == signature:
            # This signature happened to contain no - or _, so the standard
            # and url-safe alphabets agree. Nothing to reject.
            continue
        with pytest.raises(MalformedSignatureError):
            decode_signature(bad)


def test_non_canonical_slack_bit_variants_are_refused() -> None:
    """Only four final characters carry no slack bits, and one is ours.

    The 86th character holds two real bits and four slack bits. Sixteen
    characters share any given pair of real bits, and fifteen of those spell
    the *same* 64 bytes with non-zero slack - those must be refused. The four
    that survive (A, Q, g, w) are canonical, but three of them encode a
    different signature; exactly one is the one we produced.
    """
    payload = canonical_message(room="r", nonce="1", text="x")
    signature = sign_payload(payload, seed=bytes.fromhex(TEST_ONLY_SEED_A))
    raw = decode_signature(signature)

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    accepted: list[str] = []
    for final in alphabet:
        candidate = signature[:-1] + final
        try:
            decoded = decode_signature(candidate)
        except MalformedSignatureError:
            continue
        accepted.append(final)
        # Whatever is accepted must be the unique spelling of its own bytes.
        assert encode_signature(decoded) == candidate

    assert accepted == ["A", "Q", "g", "w"], (
        f"expected exactly the four zero-slack characters, got {accepted}"
    )
    # And exactly one of them is a spelling of *our* signature.
    same_bytes = [
        final for final in accepted if decode_signature(signature[:-1] + final) == raw
    ]
    assert same_bytes == [signature[-1]]


def test_encode_refuses_wrong_length_input() -> None:
    for length in (0, 32, 63, 65, 128):
        with pytest.raises(MalformedSignatureError):
            encode_signature(b"\x01" * length)


def test_decode_refuses_non_string_input() -> None:
    with pytest.raises(MalformedSignatureError):
        decode_signature(b"not a string")  # type: ignore[arg-type]


def test_is_canonical_signature_is_total() -> None:
    for bad in (None, 7, b"x", "", "a" * 85, "a" * 87):
        assert not is_canonical_signature(bad)


# --- tamper detection ------------------------------------------------------


def _signed_message() -> tuple[str, str, CanonicalPayload]:
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    payload = canonical_message(room="test-room", nonce="1", text="hello world")
    return did_key_from_seed(seed), sign_payload(payload, seed=seed), payload


def test_every_canonical_field_is_covered_by_the_signature() -> None:
    """Changing any structural field or the text must break verification."""
    did, signature, _ = _signed_message()

    tampered = [
        canonical_message(room="other-room", nonce="1", text="hello world"),
        canonical_message(room="test-room", nonce="2", text="hello world"),
        canonical_message(room="test-room", nonce="01", text="hello world"),
        canonical_message(room="test-room", nonce="1", text="hello worlds"),
        canonical_message(room="test-room", nonce="1", text="Hello world"),
    ]
    for payload in tampered:
        with pytest.raises(SignatureMismatchError):
            verify_payload(payload, did=did, signature=signature)


def test_note_fields_are_covered_by_the_signature() -> None:
    seed = bytes.fromhex(TEST_ONLY_SEED_B)
    did = did_key_from_seed(seed)
    original = canonical_note(namespace="ns", key="k", nonce="1", value="v")
    signature = sign_payload(original, seed=seed)

    for payload in (
        canonical_note(namespace="ns2", key="k", nonce="1", value="v"),
        canonical_note(namespace="ns", key="k2", nonce="1", value="v"),
        canonical_note(namespace="ns", key="k", nonce="2", value="v"),
        canonical_note(namespace="ns", key="k", nonce="1", value="v2"),
    ):
        with pytest.raises(SignatureMismatchError):
            verify_payload(payload, did=did, signature=signature)


def test_a_different_signer_is_refused() -> None:
    _, signature, payload = _signed_message()
    other_did = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEED_B))
    with pytest.raises(SignatureMismatchError):
        verify_payload(payload, did=other_did, signature=signature)


def test_malformed_and_invalid_are_different_failures() -> None:
    """Not-a-signature is a different fact from does-not-verify."""
    did, signature, payload = _signed_message()

    with pytest.raises(MalformedSignatureError):
        verify_payload(payload, did=did, signature=signature + "=")

    other = canonical_message(room="test-room", nonce="1", text="different")
    with pytest.raises(SignatureMismatchError):
        verify_payload(other, did=did, signature=signature)


def test_signing_refuses_anything_but_32_raw_bytes() -> None:
    payload = canonical_message(room="r", nonce="1", text="x")
    for bad in (b"", b"\x01" * 31, b"\x01" * 33, b"\x01" * 64):
        with pytest.raises(InvalidSeedError):
            sign_payload(payload, seed=bad)

    # A hex *string* is not a seed. Accepting one would quietly reintroduce
    # the reference's passphrase path.
    with pytest.raises(InvalidSeedError):
        sign_payload(payload, seed=TEST_ONLY_SEED_A)  # type: ignore[arg-type]


def test_signing_requires_a_canonical_payload() -> None:
    """There is no way in with a bare string."""
    with pytest.raises(TypeError):
        sign_payload(  # type: ignore[arg-type]
            "test-room|1|hello", seed=bytes.fromhex(TEST_ONLY_SEED_A)
        )


def test_an_invalid_nonce_never_reaches_the_signer() -> None:
    with pytest.raises(InvalidNonceError):
        canonical_message(room="r", nonce="١٢٣", text="x")
