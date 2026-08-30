"""The critical protocol projection, and drift against it.

A raw hash of ``/openapi.json`` would flag every typo fix as protocol drift
and would therefore be ignored within a week. What matters is narrower: the
handful of machine-readable facts a signature's validity depends on. This
module names them, states where each one lives, says why it is critical, and
compares the live value against what Station signs for.

Every JSON path below was read off the live documents and cross-checked
against the pinned reference. None is guessed.

Critical versus warning
-----------------------
**Critical** means: if this changes, a signature Station produces may be
refused by the server, or - worse - accepted over bytes the user did not
approve. Those close the write gate.

**Warning** means: the service changed something real that a user should see,
but a signature stays valid. Capacity and rate limits are the clear case; the
specification is explicit that a limit change warns rather than blocks
(§14.4), and that limits are read at runtime rather than hard-coded.

Remote values are untrusted input
---------------------------------
Authority level 1 buys accuracy, not safety. Every observed value is
truncated and stripped of control characters before it is stored or shown, so
a manifest cannot smuggle a terminal escape, a line break or a megabyte of
text into a log line, the database or the UI.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from station_api.technocore.sources import SourceId

#: Longest observed value kept. Generous for a pattern, far too small to be a
#: useful smuggling channel.
MAX_OBSERVED_CHARS = 200

#: Marker used when a document does not carry the field at all. Distinct from
#: an empty string, which would be a value the server actually published.
MISSING = "<yok>"

_INVISIBLE = frozenset({"Cc", "Cf", "Cs", "Co", "Zl", "Zp"})


class DriftState(StrEnum):
    """The four states the manifest check can report."""

    #: No live check has run in this process. The starting state, every time.
    NEVER_CHECKED = "never_checked"
    #: Every critical field matches what Station signs for.
    CURRENT = "current"
    #: At least one critical field differs. The gate closes.
    DRIFTED = "drifted"
    #: A required document could not be fetched or parsed. The gate closes.
    UNAVAILABLE = "unavailable"


class Severity(StrEnum):
    CRITICAL = "critical"
    WARNING = "warning"


class Compare(StrEnum):
    """How an observed value is judged against the expected one."""

    #: Byte-for-byte. Right for a regex or a canonical payload shape, where
    #: any difference is a different contract.
    EXACT = "exact"
    #: Every expected token must appear, case-insensitively. Right for a prose
    #: field that states a machine fact: a rewording that keeps the meaning
    #: should not be called drift, but dropping "unpadded" should.
    TOKENS = "tokens"
    #: The expected value must appear in a list.
    CONTAINS = "contains"


@dataclass(frozen=True, slots=True)
class ProtocolField:
    """One fact the live service publishes, and what Station expects."""

    key: str
    label: str
    source_id: SourceId
    #: Where the value lives, written the way a human would check it by hand.
    json_path: str
    severity: Severity
    compare: Compare
    expected: str
    #: Why a change here matters. Shown to the user, so it explains the
    #: consequence rather than restating the field name.
    rationale: str


@dataclass(frozen=True, slots=True)
class FieldObservation:
    """The verdict for one field."""

    field: ProtocolField
    observed: str
    matches: bool

    @property
    def is_critical_mismatch(self) -> bool:
        return not self.matches and self.field.severity is Severity.CRITICAL


@dataclass(frozen=True, slots=True)
class ProjectionResult:
    """The outcome of comparing the live documents with the expectation."""

    state: DriftState
    observations: tuple[FieldObservation, ...]
    #: Human-readable reasons the state is not ``current``.
    reasons: tuple[str, ...]

    @property
    def critical_mismatches(self) -> tuple[FieldObservation, ...]:
        return tuple(item for item in self.observations if item.is_critical_mismatch)

    @property
    def warnings(self) -> tuple[FieldObservation, ...]:
        return tuple(
            item
            for item in self.observations
            if not item.matches and item.field.severity is Severity.WARNING
        )


# ---------------------------------------------------------------------------
# The expected contract.
#
# These values are what Stage 2B's conformance engine signs for. They are
# pinned here rather than read from the live service on purpose: a checker
# that adopted whatever the server currently says would report "current"
# forever and detect nothing.
# ---------------------------------------------------------------------------

_MESSAGE_POST_SCHEMA = (
    "paths./r/{room}.post.requestBody.content.application/json.schema.properties"
)
_NOTE_POST_SCHEMA = (
    "paths./kv/{ns}/{key}.post.requestBody.content.application/json.schema.properties"
)

PROTOCOL_FIELDS: tuple[ProtocolField, ...] = (
    # --- the signed lanes exist at the method and path we will use ---------
    ProtocolField(
        key="signed_message_lane",
        label="Imzali mesaj yolu",
        source_id=SourceId.OPENAPI,
        json_path="paths./r/{room}.post",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="POST /r/{room}",
        rationale=(
            "Station imzali mesaji bu method ve yola gonderecek. Yol veya "
            "method degisirse imza dogru uretilse bile istek yanlis yere gider."
        ),
    ),
    ProtocolField(
        key="signed_note_lane",
        label="Imzali note yolu",
        source_id=SourceId.OPENAPI,
        json_path="paths./kv/{ns}/{key}.post",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="POST /kv/{ns}/{key}",
        rationale=(
            "Imzali note yolu. Mesajla ayni gerekce: kaybolursa veya tasinirsa "
            "Station'in planladigi lane artik yok demektir."
        ),
    ),
    # --- the patterns the server enforces on a signed write ----------------
    ProtocolField(
        key="did_pattern",
        label="DID bicimi",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA}.did.pattern",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected=r"^did:key:z6Mk[1-9A-HJ-NP-Za-km-z]{44}$",
        rationale=(
            "Sunucunun kabul ettigi DID kalibi. Degisirse Station'in urettigi "
            "did:key artik gecerli sayilmayabilir."
        ),
    ),
    ProtocolField(
        key="did_length",
        label="DID uzunlugu",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA}.did.maxLength",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="56",
        rationale=(
            "Ed25519 did:key tam 56 karakterdir; farkli bir uzunluk farkli bir "
            "sema demektir."
        ),
    ),
    ProtocolField(
        key="signature_pattern",
        label="Imza bicimi",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA}.sig.pattern",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected=r"^[A-Za-z0-9_-]{86}$",
        rationale=(
            "Padding'siz base64url, tam 86 karakter (AC-04). Bu kalip "
            "degisirse Station'in urettigi her imza reddedilir."
        ),
    ),
    ProtocolField(
        key="signature_length",
        label="Imza uzunlugu",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA}.sig.maxLength",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="86",
        rationale="64 baytlik Ed25519 imzasinin padding'siz base64url uzunlugu.",
    ),
    ProtocolField(
        key="nonce_pattern",
        label="Nonce bicimi",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA}.nonce.pattern",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected=r"^[0-9]{1,19}$",
        rationale=(
            "Nonce canonical string'in icindedir, yani imza onu kapsar. "
            "Kalip degisirse imzalanan baytlar degisir."
        ),
    ),
    ProtocolField(
        key="note_signature_pattern",
        label="Note imza bicimi",
        source_id=SourceId.OPENAPI,
        json_path=f"{_NOTE_POST_SCHEMA}.sig.pattern",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected=r"^[A-Za-z0-9_-]{86}$",
        rationale="Note lane'inin imza kalibi mesaj lane'i ile ayni olmali.",
    ),
    ProtocolField(
        key="signed_fields_required",
        label="Zorunlu imza alanlari",
        source_id=SourceId.OPENAPI,
        json_path=f"{_MESSAGE_POST_SCHEMA} (did, sig, nonce)",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="did,nonce,sig",
        rationale=(
            "Imzali lane bu uc alani birlikte tasir. Biri kaybolursa imzali "
            "yazma sozlesmesi degismis demektir."
        ),
    ),
    # --- the canonical strings a signature covers --------------------------
    ProtocolField(
        key="message_signature_payload",
        label="Mesaj canonical bicimi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="identity.message_signature_payload",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="<room>|<nonce>|<text>",
        rationale=(
            "Imzanin kapsadigi tam bayt dizisi. Alan sirasi veya ayrac "
            "degisirse Station'in imzaladigi sey sunucunun bekledigi sey olmaz."
        ),
    ),
    ProtocolField(
        key="note_signature_payload",
        label="Note canonical bicimi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="identity.note_signature_payload",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="<namespace>|<key>|<nonce>|<value>",
        rationale="Note imzasinin kapsadigi tam bayt dizisi.",
    ),
    ProtocolField(
        key="signature_encoding",
        label="Imza kodlamasi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="identity.signature_encoding",
        severity=Severity.CRITICAL,
        compare=Compare.TOKENS,
        expected="base64url 86 unpadded",
        rationale=(
            "Kodlama sozlesmesi. Ifade yeniden yazilabilir, fakat 'unpadded' "
            "veya '86' kaybolursa sozlesme gercekten degismistir."
        ),
    ),
    ProtocolField(
        key="identity_scheme",
        label="Kimlik semasi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="identity.scheme",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected="did:key",
        rationale=(
            "Station yalniz did:key uretir; baska bir sema desteklenmiyor "
            "demektir."
        ),
    ),
    ProtocolField(
        key="identity_algorithm",
        label="Imza algoritmasi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="identity.algorithms",
        severity=Severity.CRITICAL,
        compare=Compare.CONTAINS,
        expected="Ed25519",
        rationale=(
            "Station yalniz Ed25519 imzalar. Listeden cikarsa imzalarimiz "
            "gecersizdir."
        ),
    ),
    ProtocolField(
        key="name_pattern",
        label="Oda/namespace/key kalibi",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="conventions.name_pattern",
        severity=Severity.CRITICAL,
        compare=Compare.EXACT,
        expected=r"^[a-z0-9][a-z0-9_-]{0,47}$",
        rationale=(
            "Bu allow-list canonical string'i kacislama olmadan birlestirmeyi "
            "guvenli kilan seydir: yapisal alan asla '|' iceremez."
        ),
    ),
    # --- capacity: real changes, but a signature stays valid ---------------
    ProtocolField(
        key="message_chars",
        label="Mesaj karakter siniri",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="limits.message_chars",
        severity=Severity.WARNING,
        compare=Compare.EXACT,
        expected="4096",
        rationale=(
            "Kapasite degisikligi imzayi gecersiz kilmaz; kullanicinin gormesi "
            "gereken bir farktir (kunye §14.4)."
        ),
    ),
    ProtocolField(
        key="note_chars",
        label="Note karakter siniri",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="limits.note_chars",
        severity=Severity.WARNING,
        compare=Compare.EXACT,
        expected="8192",
        rationale="Mesaj siniriyla ayni gerekce.",
    ),
    ProtocolField(
        key="service_version",
        label="Servis surumu",
        source_id=SourceId.AGENT_MANIFEST,
        json_path="version",
        severity=Severity.WARNING,
        compare=Compare.EXACT,
        expected="0.10.0",
        rationale=(
            "Surum degisikligi tek basina drift degildir, fakat kritik "
            "alanlari yeniden okumak icin iyi bir sebeptir."
        ),
    ),
)


def safe_display(value: object) -> str:
    """Make a remote value safe to store, log and render.

    Control, format and separator characters become a space, and the result
    is truncated. Level-1 authority means the document is probably accurate;
    it does not mean the bytes are safe to paste into a log line or a UI.
    """
    if value is None:
        return MISSING
    if isinstance(value, bool):
        return "true" if value else "false"
    text = (
        ",".join(safe_display(item) for item in value)
        if isinstance(value, list)
        else str(value)
    )

    swept = "".join(
        " " if unicodedata.category(character) in _INVISIBLE else character
        for character in text
    ).strip()

    if len(swept) > MAX_OBSERVED_CHARS:
        return swept[:MAX_OBSERVED_CHARS] + "..."
    return swept


def read_path(document: dict[str, Any], path: str) -> Any:
    """Walk a dotted path whose segments may themselves contain dots.

    ``paths./r/{room}.post`` is a real key followed by a real key, and a naive
    ``split(".")`` would shred it. Segments are matched greedily against the
    keys actually present, so the documented path reads the same here as it
    does when a human checks it by hand.
    """
    current: Any = document
    remaining = path

    while remaining:
        if not isinstance(current, dict):
            return None
        match = _longest_key(current, remaining)
        if match is None:
            return None
        current = current[match]
        remaining = remaining[len(match) :].removeprefix(".")

    return current


def _longest_key(node: dict[str, Any], remaining: str) -> str | None:
    """The longest key of ``node`` that prefixes ``remaining`` at a boundary."""
    best: str | None = None
    for key in node:
        if (remaining == key or remaining.startswith(f"{key}.")) and (
            best is None or len(key) > len(best)
        ):
            best = key
    return best


def _extract(field: ProtocolField, document: dict[str, Any]) -> Any:
    """Read the value a field describes, including the derived ones."""
    if field.key == "signed_message_lane":
        node = read_path(document, "paths./r/{room}.post")
        return "POST /r/{room}" if isinstance(node, dict) else None
    if field.key == "signed_note_lane":
        node = read_path(document, "paths./kv/{ns}/{key}.post")
        return "POST /kv/{ns}/{key}" if isinstance(node, dict) else None
    if field.key == "signed_fields_required":
        node = read_path(document, _MESSAGE_POST_SCHEMA)
        if not isinstance(node, dict):
            return None
        return ",".join(sorted({"did", "sig", "nonce"} & set(node)))
    return read_path(document, field.json_path)


def _matches(field: ProtocolField, raw: Any) -> bool:
    if raw is None:
        return False

    if field.compare is Compare.CONTAINS:
        if not isinstance(raw, list):
            return False
        return field.expected in [str(item) for item in raw]

    text = safe_display(raw)
    if field.compare is Compare.TOKENS:
        lowered = text.lower()
        return all(token.lower() in lowered for token in field.expected.split())
    return text == field.expected


def _observe(
    field: ProtocolField, documents: dict[SourceId, dict[str, Any]]
) -> FieldObservation:
    document = documents.get(field.source_id)
    if document is None:
        return FieldObservation(field=field, observed=MISSING, matches=False)

    raw = _extract(field, document)
    return FieldObservation(
        field=field, observed=safe_display(raw), matches=_matches(field, raw)
    )


def project(documents: dict[SourceId, dict[str, Any]]) -> ProjectionResult:
    """Compare the live documents with the expected contract.

    ``documents`` holds only the sources that parsed. A missing required
    source is the caller's problem to report as ``unavailable``; this
    function marks anything absent as a mismatch rather than quietly passing
    it.
    """
    observations = tuple(_observe(field, documents) for field in PROTOCOL_FIELDS)

    critical = [item for item in observations if item.is_critical_mismatch]
    if critical:
        reasons = tuple(
            f"{item.field.label}: beklenen {item.field.expected!r}, "
            f"gorulen {item.observed!r}"
            for item in critical
        )
        return ProjectionResult(
            state=DriftState.DRIFTED, observations=observations, reasons=reasons
        )

    return ProjectionResult(
        state=DriftState.CURRENT, observations=observations, reasons=()
    )


def unavailable(reasons: tuple[str, ...]) -> ProjectionResult:
    """A verdict for a check that could not be completed."""
    return ProjectionResult(state=DriftState.UNAVAILABLE, observations=(), reasons=reasons)


__all__ = [
    "MAX_OBSERVED_CHARS",
    "MISSING",
    "PROTOCOL_FIELDS",
    "Compare",
    "DriftState",
    "FieldObservation",
    "ProjectionResult",
    "ProtocolField",
    "Severity",
    "project",
    "read_path",
    "safe_display",
    "unavailable",
]
