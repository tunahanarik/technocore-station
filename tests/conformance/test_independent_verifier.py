"""AC-05 - an independent verifier accepts our signatures.

``cryptography`` produced these signatures, so ``cryptography`` verifying them
proves little: a consistent misuse of the API would pass both ways. PyNaCl is
a binding to libsodium - a different implementation, and the same one the
official server's ``didkey.verify`` uses - so agreement is evidence.

The pinned reference vendors ``scripts/sign.py`` and ``src/store.py`` but not
``src/didkey.py``, and this stage must not silently widen the vendor pin. So
the independent verifier is PyNaCl directly, which is exactly the substitution
the task allows. Both directions are covered:

* Station signs  -> PyNaCl verifies.
* Official signer signs -> Station verifies, and PyNaCl verifies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from technocore_conform import (
    CanonicalPayload,
    canonical_message,
    canonical_note,
    decode_signature,
    did_key_from_seed,
    encode_signature,
    public_key_from_did_key,
    sign_payload,
    verify_payload,
)

from tests.conformance.oracle import official_message_signature, official_note_signature

pytestmark = pytest.mark.conformance

#: TEST-ONLY seeds. Published fixtures, never operational key material.
TEST_ONLY_SEED_A = "0000000000000000000000000000000000000000000000000000000000000001"
TEST_ONLY_SEED_B = "7e57000000000000000000000000000000000000000000000000000000000001"

MESSAGE_CASES = [
    ("test-room", "1", "hello world"),
    ("oda-1", "007", "  Türkçe ĞÜŞİÖÇ ve  bosluk  "),
    ("r", "42", "satir\nsonu"),
    ("pipes", "9", "a|b|c"),
    ("emoji", "3", "aile \U0001f468‍\U0001f469‍\U0001f467"),
]

NOTE_CASES = [
    ("profile", "bio", "1", "kisa tanitim"),
    ("ns-1", "key_1", "0007", "deger\tsekmeli"),
    ("profil", "aciklama", "88", "Türkçe değer"),
]


def _nacl_verify(payload: CanonicalPayload, *, did: str, signature: str) -> None:
    """Verify with libsodium, from the DID alone. Raises on failure."""
    verify_key = VerifyKey(public_key_from_did_key(did))
    verify_key.verify(payload.canonical_bytes, decode_signature(signature))


# --- Station signs, the independent verifier accepts ------------------------


@pytest.mark.parametrize(("room", "nonce", "text"), MESSAGE_CASES)
def test_our_message_signatures_pass_an_independent_verifier(
    room: str, nonce: str, text: str
) -> None:
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    payload = canonical_message(room=room, nonce=nonce, text=text)
    signature = sign_payload(payload, seed=seed)

    _nacl_verify(payload, did=did_key_from_seed(seed), signature=signature)


@pytest.mark.parametrize(("namespace", "key", "nonce", "value"), NOTE_CASES)
def test_our_note_signatures_pass_an_independent_verifier(
    namespace: str, key: str, nonce: str, value: str
) -> None:
    seed = bytes.fromhex(TEST_ONLY_SEED_B)
    payload = canonical_note(namespace=namespace, key=key, nonce=nonce, value=value)
    signature = sign_payload(payload, seed=seed)

    _nacl_verify(payload, did=did_key_from_seed(seed), signature=signature)


# --- the official signer's output, accepted both ways -----------------------


@pytest.mark.parametrize(("room", "nonce", "text"), MESSAGE_CASES)
def test_official_message_signatures_pass_our_verifier(
    vendor_root: Path, room: str, nonce: str, text: str
) -> None:
    did, signature = official_message_signature(
        vendor_root, seed_hex=TEST_ONLY_SEED_A, room=room, nonce=nonce, text=text
    )
    payload = canonical_message(room=room, nonce=nonce, text=text)

    verify_payload(payload, did=did, signature=signature)
    _nacl_verify(payload, did=did, signature=signature)


@pytest.mark.parametrize(("namespace", "key", "nonce", "value"), NOTE_CASES)
def test_official_note_signatures_pass_our_verifier(
    vendor_root: Path, namespace: str, key: str, nonce: str, value: str
) -> None:
    did, signature = official_note_signature(
        vendor_root,
        seed_hex=TEST_ONLY_SEED_B,
        namespace=namespace,
        key=key,
        nonce=nonce,
        value=value,
    )
    payload = canonical_note(namespace=namespace, key=key, nonce=nonce, value=value)

    verify_payload(payload, did=did, signature=signature)
    _nacl_verify(payload, did=did, signature=signature)


def test_the_did_resolves_to_the_same_public_key_both_ways(vendor_root: Path) -> None:
    """Our did:key resolution and the reference's agree on the key bytes."""
    did, _ = official_message_signature(
        vendor_root, seed_hex=TEST_ONLY_SEED_A, room="r", nonce="1", text="x"
    )
    assert did == did_key_from_seed(bytes.fromhex(TEST_ONLY_SEED_A))
    assert bytes(VerifyKey(public_key_from_did_key(did))) == public_key_from_did_key(did)


# --- the independent verifier must also reject ------------------------------


def test_the_independent_verifier_rejects_tampered_payloads() -> None:
    """A verifier that accepted everything would prove nothing above."""
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    did = did_key_from_seed(seed)
    original = canonical_message(room="test-room", nonce="1", text="hello world")
    signature = sign_payload(original, seed=seed)

    for tampered in (
        canonical_message(room="other-room", nonce="1", text="hello world"),
        canonical_message(room="test-room", nonce="2", text="hello world"),
        canonical_message(room="test-room", nonce="1", text="hello worlds"),
    ):
        with pytest.raises(BadSignatureError):
            _nacl_verify(tampered, did=did, signature=signature)


def test_the_independent_verifier_rejects_another_signers_key() -> None:
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    payload = canonical_message(room="test-room", nonce="1", text="hello world")
    signature = sign_payload(payload, seed=seed)
    other_did = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEED_B))

    with pytest.raises(BadSignatureError):
        _nacl_verify(payload, did=other_did, signature=signature)


def test_raw_text_signatures_are_rejected_against_stored_text() -> None:
    """The 403 case, proved locally against an independent implementation."""
    seed = bytes.fromhex(TEST_ONLY_SEED_A)
    raw = "  bosluklu\nmetin  "
    payload = canonical_message(room="r", nonce="1", text=raw)

    raw_signature = encode_signature(
        Ed25519PrivateKey.from_private_bytes(seed).sign(f"r|1|{raw}".encode())
    )
    with pytest.raises(BadSignatureError):
        _nacl_verify(payload, did=did_key_from_seed(seed), signature=raw_signature)
