"""Runtime conformance self-test.

This is what the write gate consults. It answers one narrow question:

    Does the code running *right now, on this machine* still reproduce the
    behaviour of the pinned official reference?

It answers it by replaying vectors that were derived from that reference and
shipped inside this package. That matters on two counts: the check needs no
``vendor/`` directory and no network, so it runs on an end user's machine; and
it is a real check rather than a recorded verdict, because every vector is
recomputed here from the seed and the input text.

What a pass does **not** mean
-----------------------------
It means "conformant with the pinned reference commit". It says nothing about
whether the live Technocore server is still on that protocol - that is
manifest drift, a separate Stage 3 check that stays closed until it exists.
Conflating the two would be the exact dishonesty the write gate is built to
prevent.

Fail-closed, twice over
-----------------------
1. The vector bundle's SHA-256 is pinned in this module. Editing the vectors
   to make a failing check pass changes the digest, and the digest check
   fails instead. There is no path where weakening the vectors weakens the
   gate.
2. ``run_self_test`` never raises. A missing bundle, a bad digest or an
   unexpected exception all produce ``passed=False`` with the reason
   recorded. A caller cannot accidentally treat a crash as a pass.

The Unicode database is part of the result
------------------------------------------
The sweep is defined in terms of Unicode general categories, so its output
depends on the Unicode database the running Python was built against. If that
differs from the version the vectors were generated under, characters outside
our vector set could sweep differently and we would have no evidence either
way. That is reported as a failure, not waved through.
"""

from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
from dataclasses import dataclass
from importlib import resources
from typing import Any

from technocore_conform._version import __version__
from technocore_conform.canonical import (
    CanonicalPayload,
    canonical_message_from_swept,
    canonical_note_from_swept,
)
from technocore_conform.did import did_key_from_seed
from technocore_conform.errors import ConformanceError, SelfTestError
from technocore_conform.signature import (
    SIGNATURE_CHARS,
    decode_signature,
    encode_signature,
    is_canonical_signature,
    sign_payload,
    verify_payload,
)
from technocore_conform.sweep import MESSAGE_POLICY, NOTE_VALUE_POLICY, sweep

#: Package subdirectory holding the shipped vectors.
VECTOR_PACKAGE = "technocore_conform.vectors"

#: The shipped vector bundle.
VECTOR_FILENAME = "conformance-v1.json"

#: SHA-256 of the shipped bundle, pinned here so the vectors cannot be edited
#: to manufacture a pass. Regenerated only alongside the vendor pin, and
#: checked by tests/conformance/test_vectors.py against the live oracle.
EXPECTED_BUNDLE_DIGEST = "688c6e4dcf14eeed05f83381b3eb740419a4edff0392f9de146d2032034c2af0"

EXPECTED_BUNDLE_FORMAT = "technocore-conformance-vectors"
EXPECTED_BUNDLE_VERSION = 1

_POLICIES = {"message": MESSAGE_POLICY, "note_value": NOTE_VALUE_POLICY}


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One named area of the contract, and how many vectors it covered."""

    name: str
    passed: bool
    vectors: int
    detail: str


@dataclass(frozen=True, slots=True)
class SelfTestResult:
    """The whole verdict, plus everything needed to interpret it later."""

    passed: bool
    checks: tuple[CheckResult, ...]
    failures: tuple[str, ...]
    bundle_digest: str
    bundle_vectors: int
    upstream_commit: str
    package_version: str
    python_version: str
    unicode_version: str
    bundle_unicode_version: str

    @property
    def unicode_version_matches(self) -> bool:
        return self.unicode_version == self.bundle_unicode_version

    @property
    def capabilities(self) -> tuple[str, ...]:
        """The contract areas that passed, for display."""
        return tuple(check.name for check in self.checks if check.passed)


def _load_bundle() -> tuple[dict[str, Any], str]:
    """Read and integrity-check the shipped bundle.

    Returns the parsed bundle and its digest. Raises ``SelfTestError`` when
    the bundle is missing, unreadable, or not the pinned one.
    """
    try:
        payload = resources.files(VECTOR_PACKAGE).joinpath(VECTOR_FILENAME).read_bytes()
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise SelfTestError("conformance vector bundle is missing") from exc

    actual = hashlib.sha256(payload).hexdigest()
    if actual != EXPECTED_BUNDLE_DIGEST:
        raise SelfTestError(
            f"conformance vector bundle digest mismatch: expected "
            f"{EXPECTED_BUNDLE_DIGEST[:12]}, found {actual[:12]}"
        )

    bundle: dict[str, Any] = json.loads(payload.decode("ascii"))
    if bundle.get("format") != EXPECTED_BUNDLE_FORMAT:
        raise SelfTestError("conformance vector bundle has an unexpected format")
    if bundle.get("version") != EXPECTED_BUNDLE_VERSION:
        raise SelfTestError("conformance vector bundle has an unexpected version")
    return bundle, actual


def _check_sweep(bundle: dict[str, Any]) -> CheckResult:
    """Replay every sweep vector, including the refusals."""
    vectors = bundle["sweep"]
    for vector in vectors:
        policy = _POLICIES[vector["policy"]]
        if vector["outcome"] == "refused":
            try:
                sweep(vector["input"], policy)
            except ConformanceError:
                continue
            return CheckResult(
                "sweep", False, len(vectors), f"vector {vector['id']} should be refused"
            )
        try:
            produced = sweep(vector["input"], policy)
        except ConformanceError as exc:
            return CheckResult(
                "sweep", False, len(vectors), f"vector {vector['id']} refused: {exc}"
            )
        if produced != vector["output"]:
            return CheckResult(
                "sweep", False, len(vectors), f"vector {vector['id']} swept differently"
            )
        # Idempotence, checked at runtime rather than assumed (AC-03).
        if sweep(produced, policy) != produced:
            return CheckResult(
                "sweep", False, len(vectors), f"vector {vector['id']} is not idempotent"
            )
    return CheckResult("sweep", True, len(vectors), "swept text matches the reference")


def _check_did(bundle: dict[str, Any]) -> CheckResult:
    vectors = bundle["did"]
    for vector in vectors:
        if did_key_from_seed(bytes.fromhex(vector["seed_hex"])) != vector["did"]:
            return CheckResult("did", False, len(vectors), "did:key derivation diverged")
    return CheckResult("did", True, len(vectors), "did:key matches the reference")


def _payload_for(vector: dict[str, Any], kind: str) -> CanonicalPayload:
    if kind == "message":
        return canonical_message_from_swept(
            room=vector["room"], nonce=vector["nonce"], swept_text=vector["swept_text"]
        )
    return canonical_note_from_swept(
        namespace=vector["namespace"],
        key=vector["key"],
        nonce=vector["nonce"],
        swept_value=vector["swept_value"],
    )


def _check_canonical(bundle: dict[str, Any]) -> CheckResult:
    """The canonical string must be byte-identical, rebuilt from stored text."""
    vectors = [*bundle["message"], *bundle["note"]]
    for kind in ("message", "note"):
        for vector in bundle[kind]:
            payload = _payload_for(vector, kind)
            if payload.canonical != vector["canonical"]:
                return CheckResult(
                    "canonical", False, len(vectors), f"vector {vector['id']} diverged"
                )
            if payload.canonical_bytes != vector["canonical"].encode("utf-8"):
                return CheckResult(
                    "canonical", False, len(vectors), f"vector {vector['id']} bytes diverged"
                )
    return CheckResult("canonical", True, len(vectors), "canonical bytes match the reference")


def _check_signing(bundle: dict[str, Any]) -> CheckResult:
    """Re-sign each vector and compare with the reference's own signature.

    Ed25519 is deterministic, so this is an equality check, not a "some valid
    signature" check.
    """
    vectors = [*bundle["message"], *bundle["note"]]
    for kind in ("message", "note"):
        for vector in bundle[kind]:
            payload = _payload_for(vector, kind)
            produced = sign_payload(payload, seed=bytes.fromhex(vector["seed_hex"]))
            if produced != vector["signature"]:
                return CheckResult(
                    "signing", False, len(vectors), f"vector {vector['id']} signed differently"
                )
    return CheckResult("signing", True, len(vectors), "signatures match the reference")


def _check_verification(bundle: dict[str, Any]) -> CheckResult:
    vectors = [*bundle["message"], *bundle["note"]]
    for kind in ("message", "note"):
        for vector in bundle[kind]:
            payload = _payload_for(vector, kind)
            try:
                verify_payload(payload, did=vector["did"], signature=vector["signature"])
            except ConformanceError as exc:
                return CheckResult(
                    "verification", False, len(vectors), f"vector {vector['id']}: {exc}"
                )
    return CheckResult("verification", True, len(vectors), "reference signatures verify")


def _check_encoding(bundle: dict[str, Any]) -> CheckResult:
    """The canonical unpadded base64url contract (AC-04)."""
    vectors = [*bundle["message"], *bundle["note"]]
    for vector in vectors:
        signature = vector["signature"]
        if len(signature) != SIGNATURE_CHARS or not is_canonical_signature(signature):
            return CheckResult(
                "encoding", False, len(vectors), f"vector {vector['id']} is not canonical"
            )
        raw = decode_signature(signature)
        if len(raw) != 64 or encode_signature(raw) != signature:
            return CheckResult(
                "encoding", False, len(vectors), f"vector {vector['id']} fails round-trip"
            )
        # A padded spelling of the same bytes must be refused.
        try:
            decode_signature(signature + "==")
        except ConformanceError:
            continue
        return CheckResult("encoding", False, len(vectors), "a padded signature was accepted")
    return CheckResult("encoding", True, len(vectors), "signatures are canonical base64url")


def _tampered_payload(
    vector: dict[str, Any], base: dict[str, Any], kind: str
) -> tuple[CanonicalPayload, str]:
    """Apply one mutation and return the payload plus the DID to verify with."""
    mutated = dict(base)
    did = str(base["did"])
    field = vector["field"]
    if field == "did":
        did = str(vector["value"])
    elif field == "text":
        mutated["swept_text"] = vector["value"]
    elif field == "value":
        mutated["swept_value"] = vector["value"]
    else:
        mutated[field] = vector["value"]
    return _payload_for(mutated, kind), did


def _check_tamper(bundle: dict[str, Any]) -> CheckResult:
    """Every single-field mutation must fail verification."""
    vectors = bundle["tamper"]
    index = {
        kind: {item["id"]: item for item in bundle[kind]} for kind in ("message", "note")
    }
    for vector in vectors:
        kind = vector["base_kind"]
        base = index[kind][vector["base_id"]]
        payload, did = _tampered_payload(vector, base, kind)
        try:
            verify_payload(payload, did=did, signature=base["signature"])
        except ConformanceError:
            continue
        return CheckResult(
            "tamper", False, len(vectors), f"tampered vector {vector['id']} verified"
        )
    return CheckResult("tamper", True, len(vectors), "every tampered payload is refused")


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _failed(reason: str, digest: str = "") -> SelfTestResult:
    """A result that cannot be mistaken for a pass."""
    return SelfTestResult(
        passed=False,
        checks=(),
        failures=(reason,),
        bundle_digest=digest,
        bundle_vectors=0,
        upstream_commit="",
        package_version=__version__,
        python_version=_python_version(),
        unicode_version=unicodedata.unidata_version,
        bundle_unicode_version="",
    )


def run_self_test() -> SelfTestResult:
    """Run every check. Never raises; a failure is reported, not thrown."""
    try:
        bundle, bundle_digest = _load_bundle()
    except SelfTestError as exc:
        return _failed(str(exc))
    except Exception as exc:
        # Broad on purpose: a self-test must never crash its caller, or a
        # caller's except-block could turn the crash into an apparent pass.
        return _failed(f"conformance vector bundle could not be read: {exc!r}")

    try:
        checks = [
            _check_sweep(bundle),
            _check_did(bundle),
            _check_canonical(bundle),
            _check_signing(bundle),
            _check_verification(bundle),
            _check_encoding(bundle),
            _check_tamper(bundle),
        ]
    except Exception as exc:
        # Broad for the same reason as above.
        return _failed(f"conformance self-test raised: {exc!r}", bundle_digest)

    bundle_unicode = str(bundle.get("unicode_version", ""))
    runtime_unicode = unicodedata.unidata_version
    if bundle_unicode != runtime_unicode:
        # Not waved through: the sweep is defined over Unicode categories, so
        # a different database could classify characters our vectors never
        # covered. We have no evidence, so we do not claim conformance.
        checks.append(
            CheckResult(
                "unicode_database",
                False,
                0,
                f"vectors were generated under Unicode {bundle_unicode}, "
                f"this runtime uses {runtime_unicode}",
            )
        )
    else:
        checks.append(CheckResult("unicode_database", True, 0, f"Unicode {runtime_unicode}"))

    failures = tuple(f"{check.name}: {check.detail}" for check in checks if not check.passed)
    return SelfTestResult(
        passed=not failures,
        checks=tuple(checks),
        failures=failures,
        bundle_digest=bundle_digest,
        bundle_vectors=sum(check.vectors for check in checks),
        upstream_commit=str(bundle.get("upstream_commit", "")),
        package_version=__version__,
        python_version=_python_version(),
        unicode_version=runtime_unicode,
        bundle_unicode_version=bundle_unicode,
    )


__all__ = [
    "EXPECTED_BUNDLE_DIGEST",
    "EXPECTED_BUNDLE_FORMAT",
    "EXPECTED_BUNDLE_VERSION",
    "VECTOR_FILENAME",
    "VECTOR_PACKAGE",
    "CheckResult",
    "SelfTestResult",
    "run_self_test",
]
