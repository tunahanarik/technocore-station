"""Build the runtime conformance vector bundle from the pinned oracles.

The bundle shipped inside ``technocore_conform`` is what the runtime
self-test checks itself against on a machine that has no ``vendor/``
directory. It must therefore be *derived from* the official reference, not
written by hand - otherwise the self-test would only confirm that this
project agrees with itself.

This module is the derivation. ``tests/conformance/test_vectors.py`` runs it
against the pinned oracle and asserts the result is byte-identical to the
shipped file, so the claim "these vectors came from the reference" is checked
on every test run rather than trusted.

Every seed here is a published TEST-ONLY fixture. They are deliberately
*different* from the canary seed in ``tests/conftest.py``: that canary proves
a seed never escapes the vault, and reusing it here would put it in a shipped
file and make the leak search meaningless.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

from tests.conformance.oracle import (
    PINNED_COMMIT,
    load_official_sweep,
    official_did,
    official_limits,
    official_message_signature,
    official_name_pattern,
    official_nonce_pattern,
    official_note_signature,
)

BUNDLE_FORMAT = "technocore-conformance-vectors"
BUNDLE_VERSION = 1

#: TEST-ONLY seeds. Published fixtures, never operational key material, and
#: deliberately not the leak-detection canary from tests/conftest.py.
TEST_ONLY_SEEDS: tuple[str, ...] = (
    "0000000000000000000000000000000000000000000000000000000000000001",
    "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff",
    "7e57000000000000000000000000000000000000000000000000000000000001",
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
)

#: ``(id, policy, text)``. The policy selects which limit applies.
#:
#: The list covers every hazard class the sweep exists for, plus the cases
#: where a plausible implementation would diverge: no-collapse, trim-only,
#: an interior no-break space, and text that survives untouched.
_SWEEP_CASES: tuple[tuple[str, str, str], ...] = (
    ("ascii-plain", "message", "hello world"),
    ("ascii-trim", "message", "   hello world   "),
    ("ascii-interior-spaces", "message", "hello   world"),
    ("turkish", "message", "İstanbul'da ĞÜŞİÖÇ ğüşiöç yazı"),
    ("emoji-zwj", "message", "aile: \U0001f468‍\U0001f469‍\U0001f467 son"),
    ("emoji-plain", "message", "merhaba \U0001f600 dunya"),
    ("newline", "message", "birinci\nikinci"),
    ("crlf", "message", "birinci\r\nikinci"),
    ("tab", "message", "a\tb"),
    ("control-run", "message", "a\x00\x00\x00b"),
    ("bidi-override", "message", "normal ‮ desrever ‬ son"),
    ("unicode-tag", "message", "gizli\U000e0041\U000e0042talimat"),
    ("private-use", "message", "ab\U000f0000c"),
    ("zero-width", "message", "a​b‌c‍d"),
    ("line-separator", "message", "a\u2028b\u2029c"),
    ("nbsp-interior", "message", "a\u00a0b"),
    ("nbsp-edges", "message", "\u00a0abc\u00a0"),
    ("pipe-in-text", "message", "a|b|c"),
    ("pipe-only-text", "message", "|"),
    ("astral", "message", "\U0001d11e \U00020bb7 son"),
    ("combining", "message", "é vs é"),
    ("note-plain", "note_value", "profil degeri"),
    ("note-pipe", "note_value", "anahtar|deger"),
    ("note-control", "note_value", "a\x01\x02b"),
)

#: ``(id, seed_index, room, nonce, text)``
_MESSAGE_CASES: tuple[tuple[str, int, str, str, str], ...] = (
    ("msg-ascii", 0, "test-room", "1", "hello world"),
    ("msg-trim", 0, "test-room", "42", "   bosluklu mesaj   "),
    ("msg-turkish", 1, "oda-1", "1000", "İstanbul'dan selam, ĞÜŞİÖÇ"),
    (
        "msg-emoji-zwj",
        1,
        "oda_2",
        "999",
        "aile \U0001f468‍\U0001f469‍\U0001f467 burada",
    ),
    ("msg-control", 2, "r", "7", "satir\nsonu\tvar"),
    ("msg-bidi", 2, "room-with-dashes", "0", "trojan ‮ source ‬"),
    ("msg-pipe", 3, "a1", "0000000000000000001", "pipe|icinde|metin"),
    ("msg-nonce-max", 3, "z9", "9999999999999999999", "en buyuk nonce"),
    ("msg-leading-zero", 0, "test-room", "007", "leading zero korunur"),
    ("msg-name-max", 1, "a" * 48, "5", "en uzun oda adi"),
)

#: ``(id, seed_index, namespace, key, nonce, value)``
_NOTE_CASES: tuple[tuple[str, int, str, str, str, str], ...] = (
    ("note-ascii", 0, "profile", "bio", "1", "kisa bir tanitim"),
    ("note-turkish", 1, "profil", "aciklama", "2", "Türkçe değer: ĞÜŞİÖÇ"),
    ("note-control", 2, "ns-1", "key_1", "10", "deger\nikinci satir"),
    ("note-pipe", 3, "ns2", "k2", "0007", "a|b|c"),
    ("note-zero-width", 0, "profile", "tag", "88", "gizli​karakter"),
)

#: ``(id, base_kind, base_id, field, replacement)``. Each applies exactly one
#: mutation to a verified vector and must then fail to verify.
_TAMPER_CASES: tuple[tuple[str, str, str, str, str], ...] = (
    ("tamper-room", "message", "msg-ascii", "room", "other-room"),
    ("tamper-nonce", "message", "msg-ascii", "nonce", "2"),
    ("tamper-nonce-zero", "message", "msg-leading-zero", "nonce", "7"),
    ("tamper-text", "message", "msg-ascii", "text", "hello worlds"),
    ("tamper-did", "message", "msg-ascii", "did", ""),
    ("tamper-namespace", "note", "note-ascii", "namespace", "other"),
    ("tamper-key", "note", "note-ascii", "key", "other"),
    ("tamper-value", "note", "note-ascii", "value", "farkli bir tanitim"),
)

_POLICY_LIMIT_FIELD = {"message": 0, "note_value": 1}


def _sweep_vector(
    clean: Any, case_id: str, policy: str, text: str, limits: tuple[int, int]
) -> dict[str, Any]:
    """One sweep vector, with the reference's own verdict recorded."""
    limit = limits[_POLICY_LIMIT_FIELD[policy]]
    try:
        output = clean(text, limit)
    except Exception:
        return {"id": case_id, "policy": policy, "input": text, "outcome": "refused"}
    return {
        "id": case_id,
        "policy": policy,
        "input": text,
        "outcome": "swept",
        "output": output,
    }


def _boundary_cases(limits: tuple[int, int]) -> tuple[tuple[str, str, str], ...]:
    """Exact accept/reject boundaries, built from the reference's own limits."""
    message_limit, note_limit = limits
    return (
        ("message-at-limit", "message", "a" * message_limit),
        ("message-over-limit", "message", "a" * (message_limit + 1)),
        ("note-at-limit", "note_value", "b" * note_limit),
        ("note-over-limit", "note_value", "b" * (note_limit + 1)),
        # Trimming happens after replacement, so the padded form still lands
        # exactly on the limit: a real off-by-one trap.
        ("message-at-limit-padded", "message", "  " + "c" * message_limit + "  "),
        ("empty", "message", ""),
        ("only-invisible", "message", "​‌‍"),
        ("only-spaces", "message", "     "),
    )


def build_bundle(vendor_root: Path) -> dict[str, Any]:
    """Derive the whole bundle from the pinned reference."""
    clean = load_official_sweep(vendor_root)
    limits = official_limits(vendor_root)

    sweep_vectors = [
        _sweep_vector(clean, case_id, policy, text, limits)
        for case_id, policy, text in (*_SWEEP_CASES, *_boundary_cases(limits))
    ]

    did_vectors = [
        {"seed_hex": seed_hex, "did": official_did(vendor_root, seed_hex)}
        for seed_hex in TEST_ONLY_SEEDS
    ]

    message_vectors: list[dict[str, Any]] = []
    for case_id, seed_index, room, nonce, text in _MESSAGE_CASES:
        seed_hex = TEST_ONLY_SEEDS[seed_index]
        did, signature = official_message_signature(
            vendor_root, seed_hex=seed_hex, room=room, nonce=nonce, text=text
        )
        swept = clean(text, limits[0])
        message_vectors.append(
            {
                "id": case_id,
                "seed_hex": seed_hex,
                "did": did,
                "room": room,
                "nonce": nonce,
                "text": text,
                "swept_text": swept,
                "canonical": f"{room}|{nonce}|{swept}",
                "signature": signature,
            }
        )

    note_vectors: list[dict[str, Any]] = []
    for case_id, seed_index, namespace, key, nonce, value in _NOTE_CASES:
        seed_hex = TEST_ONLY_SEEDS[seed_index]
        did, signature = official_note_signature(
            vendor_root,
            seed_hex=seed_hex,
            namespace=namespace,
            key=key,
            nonce=nonce,
            value=value,
        )
        swept = clean(value, limits[1])
        note_vectors.append(
            {
                "id": case_id,
                "seed_hex": seed_hex,
                "did": did,
                "namespace": namespace,
                "key": key,
                "nonce": nonce,
                "value": value,
                "swept_value": swept,
                "canonical": f"{namespace}|{key}|{nonce}|{swept}",
                "signature": signature,
            }
        )

    # A DID that is valid but belongs to a different seed, for the "signed by
    # someone else" tamper case.
    other_did = did_vectors[-1]["did"]
    tamper_vectors = [
        {
            "id": case_id,
            "base_kind": base_kind,
            "base_id": base_id,
            "field": field,
            "value": other_did if field == "did" else replacement,
        }
        for case_id, base_kind, base_id, field, replacement in _TAMPER_CASES
    ]

    return {
        "format": BUNDLE_FORMAT,
        "version": BUNDLE_VERSION,
        # Deliberately not called "note": that key holds the note vectors, and
        # a second "note" entry silently overwrote them in the emitted JSON.
        "description": (
            "TEST-ONLY conformance vectors, derived from the pinned official reference. "
            "Every seed here is a published fixture and must never be used for anything real."
        ),
        "upstream_repo": "https://github.com/flop-labs/technocore-chat",
        "upstream_commit": PINNED_COMMIT,
        "unicode_version": unicodedata.unidata_version,
        "name_pattern": official_name_pattern(vendor_root),
        "nonce_pattern": official_nonce_pattern(vendor_root),
        "max_message_chars": limits[0],
        "max_note_value_chars": limits[1],
        "sweep": sweep_vectors,
        "did": did_vectors,
        "message": message_vectors,
        "note": note_vectors,
        "tamper": tamper_vectors,
    }


def serialise(bundle: dict[str, Any]) -> bytes:
    """Deterministic bytes for the bundle.

    ``ensure_ascii=True`` is required, not cosmetic: it is what lets a lone
    surrogate survive the round-trip as a ``\\udXXX`` escape instead of
    failing to encode.
    """
    text = json.dumps(bundle, sort_keys=True, indent=2, ensure_ascii=True)
    return (text + "\n").encode("ascii")


def digest(payload: bytes) -> str:
    """Lowercase hex SHA-256 of the serialised bundle."""
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "BUNDLE_FORMAT",
    "BUNDLE_VERSION",
    "TEST_ONLY_SEEDS",
    "build_bundle",
    "digest",
    "serialise",
]
