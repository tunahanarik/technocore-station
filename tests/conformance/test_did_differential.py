"""AC-01 - our did:key must equal the pinned official reference, exactly.

This is a real differential test: it runs
``vendor/technocore-reference/scripts/sign.py`` as a subprocess and compares
its output character for character with ours. The reference is the oracle; we
never copy its implementation.

Every seed here is a published TEST-ONLY fixture. No operational key material
appears in this file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from technocore_conform import (
    DID_KEY_ED25519_PREFIX,
    MULTIBASE_LENGTH,
    PUBLIC_KEY_LENGTH,
    InvalidDidError,
    InvalidPublicKeyError,
    InvalidSeedError,
    did_key_from_public_key,
    did_key_from_seed,
    fingerprint_from_public_key,
    public_key_from_did_key,
    public_key_from_seed,
)

pytestmark = pytest.mark.conformance

#: TEST-ONLY seeds. Published fixtures, never operational key material.
#: Includes the all-zero and all-0xff edges, where a naive base58 encoder that
#: mishandles leading zeros would diverge from the reference.
TEST_ONLY_SEEDS = (
    "00" * 32,
    "01" * 32,
    "ff" * 32,
    "0000000000000000000000000000000000000000000000000000000000000001",
    "4c7a1e9b3d5f8027a6c4e91b2d8f0356749ace1b2d4f6081a3c5e7092b4d6f81",
    "deadbeef" * 8,
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
)


def _oracle_did(repo_root: Path, seed_hex: str) -> str:
    """Ask the pinned official signer for the did:key of a seed."""
    script = repo_root / "vendor" / "technocore-reference" / "scripts" / "sign.py"
    result = subprocess.run(
        [sys.executable, str(script), "did", "--seed", seed_hex],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0:  # pragma: no cover - surfaces a broken oracle
        pytest.fail(f"reference signer failed: {result.stderr[:400]}")
    return result.stdout.strip()


@pytest.mark.parametrize("seed_hex", TEST_ONLY_SEEDS)
def test_did_matches_official_reference(repo_root: Path, seed_hex: str) -> None:
    assert did_key_from_seed(bytes.fromhex(seed_hex)) == _oracle_did(repo_root, seed_hex)


def test_public_key_is_exactly_32_bytes() -> None:
    for seed_hex in TEST_ONLY_SEEDS:
        assert len(public_key_from_seed(bytes.fromhex(seed_hex))) == PUBLIC_KEY_LENGTH


def test_did_structure_matches_the_specification() -> None:
    did = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEEDS[4]))
    assert did.startswith(DID_KEY_ED25519_PREFIX)
    assert len(did.removeprefix("did:key:")) == MULTIBASE_LENGTH


def test_did_round_trips_back_to_the_public_key() -> None:
    for seed_hex in TEST_ONLY_SEEDS:
        seed = bytes.fromhex(seed_hex)
        assert public_key_from_did_key(did_key_from_seed(seed)) == public_key_from_seed(seed)


@pytest.mark.parametrize("length", [0, 1, 16, 31, 33, 64])
def test_invalid_seed_length_is_refused(length: int) -> None:
    with pytest.raises(InvalidSeedError):
        did_key_from_seed(b"\x01" * length)


@pytest.mark.parametrize("length", [0, 31, 33])
def test_invalid_public_key_length_is_refused(length: int) -> None:
    with pytest.raises(InvalidPublicKeyError):
        did_key_from_public_key(b"\x02" * length)


def test_invalid_did_prefix_is_refused() -> None:
    valid = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEEDS[0]))
    for broken in (
        valid.replace("did:key:", "did:web:"),
        valid.removeprefix("did:key:"),
        "",
    ):
        with pytest.raises(InvalidDidError):
            public_key_from_did_key(broken)


def test_invalid_did_length_is_refused() -> None:
    valid = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEEDS[0]))
    with pytest.raises(InvalidDidError):
        public_key_from_did_key(valid[:-1])
    with pytest.raises(InvalidDidError):
        public_key_from_did_key(valid + "1")


def test_non_base58_characters_are_refused() -> None:
    valid = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEEDS[0]))
    # 0, O, I and l are excluded from the base58btc alphabet by design.
    for bad_char in ("0", "O", "I", "l"):
        with pytest.raises(InvalidDidError):
            public_key_from_did_key(valid[:-1] + bad_char)


def test_non_canonical_encoding_is_refused() -> None:
    """Exactly one spelling per key.

    Flipping a character keeps the length and the alphabet valid but yields a
    payload that no longer re-encodes to the same string, or is not an
    ed25519-pub key. Either way it must be rejected.
    """
    valid = did_key_from_seed(bytes.fromhex(TEST_ONLY_SEEDS[0]))
    body = valid.removeprefix("did:key:z")
    swapped = ("2" if body[0] != "2" else "3") + body[1:]
    with pytest.raises(InvalidDidError):
        public_key_from_did_key("did:key:z" + swapped)


def test_fingerprint_is_stable_and_public() -> None:
    seed = bytes.fromhex(TEST_ONLY_SEEDS[4])
    public_key = public_key_from_seed(seed)
    first = fingerprint_from_public_key(public_key)
    assert first == fingerprint_from_public_key(public_key)
    assert len(first) == 64
    # The fingerprint is derived from public material only.
    assert seed.hex() not in first
