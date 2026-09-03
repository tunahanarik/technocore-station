"""The three-step approval chain, and the only path to an outbound write.

    1. ``draft``  sweep the text, show the difference, bind a digest.
    2. ``sign``   re-run the gate, reserve a nonce, build the canonical
                  string, sign it, mint a single-use approval.
    3. ``send``   re-run the gate, spend the approval, POST once.

Three requests rather than one, because the user has to approve two different
things and they are not the same thing (ADR-0002 2). Step 1's approval is
about *content*: this is the text that will be stored, and here is how the
sweep changed what you typed. Step 2's approval is about *publication*: these
exact bytes, signed by this key, to this room, now. Collapsing them would
mean the user pressing one button for both.

What re-runs at every step
--------------------------
The whole write gate: identity present, not revoked, vault present, recovery
restore-tested, conformance self-test passed, manifest checked and current.
Not because the UI cannot disable a button, but because a disabled button is
not a control - the state can change between two of these requests, and only
the server is in a position to notice.

What an approval cannot survive
-------------------------------
Editing the text or the room (the draft digest changes), a new manifest check
(the verdict identity changes), a different identity (the DID changes), three
minutes (the TTL), a second use (single-use), and another browser session
(the session binding). Every one of those is checked at send time against a
value captured at signing time.

What this module cannot do
--------------------------
Reach a seed. The vault lives behind :mod:`station_api.compose.signer`, which
takes a payload and returns a signature; nothing here can ask it for key
material, and no LLM or agent worker has a path to either.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from technocore_conform import (
    MESSAGE_POLICY,
    CanonicalPayload,
    SweepError,
    canonical_message,
    is_canonical_signature,
    is_swept,
    sweep,
    verify_payload,
)
from technocore_conform.errors import ConformanceError

from station_api.compose.approvals import (
    SEND_TOKEN_TTL_SECONDS,
    Draft,
    DraftStore,
    SendApproval,
    canonical_digest,
    draft_digest,
)
from station_api.compose.nonce import (
    NonceReservation,
    NonceReservationError,
    NonceReserver,
    NonceStorageError,
)
from station_api.compose.signer import MessageSigner
from station_api.db.models import WriteOutcomeValue
from station_api.identity.service import IdentityServiceError, SigningIdentity
from station_api.identity.write_gate import WriteGateStatus
from station_api.logging_setup import forget_secret, register_secret
from station_api.security.tokens import SingleUseStore
from station_api.technocore.projection import PLANNED_BODY_FIELDS, Lane, SentLength
from station_api.technocore.service import TechnocoreService, TechnocoreStatus
from station_api.technocore.write_client import (
    SignedWriteClient,
    WriteOutcome,
    WriteResult,
)
from station_api.technocore.write_targets import (
    RoomPolicyError,
    WriteTarget,
    resolve_message_target,
)
from station_api.vault.errors import VaultError, VaultUnlockError

#: The field names a signed message body carries, taken from the projection
#: rather than restated here. ``from`` is deliberately absent: the reference
#: ignores it on the signed lane, so sending it would add a field nothing
#: validates and the signature does not cover.
MESSAGE_BODY_FIELDS = PLANNED_BODY_FIELDS[Lane.MESSAGE_BODY]

#: The payload field on the message lane.
PAYLOAD_FIELD = "text"


class ComposeIdentity(Protocol):
    """The two things the composer asks the identity layer for.

    Narrow on purpose. The composer needs to know whether the gate is open
    and which key will sign; it has no business with vault capabilities,
    recovery files or the lifecycle, and a dependency that named the whole
    service would be one that could grow into them.
    ``IdentityService`` satisfies this structurally.
    """

    def write_gate_status(self) -> WriteGateStatus:
        """Re-evaluate every precondition, now."""
        ...  # pragma: no cover - protocol declaration

    def active_signing_identity(self) -> SigningIdentity:
        """The active identity's vault handle and DID."""
        ...  # pragma: no cover - protocol declaration


class ComposeError(Exception):
    """A composer step was refused. The message is safe to show a user."""

    def __init__(self, message: str, *, reason: str, status_code: int) -> None:
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


def _gate_closed(detail: str) -> ComposeError:
    return ComposeError(detail, reason="write_gate_closed", status_code=409)


def _approval_rejected(detail: str, *, reason: str) -> ComposeError:
    return ComposeError(detail, reason=reason, status_code=409)


def _bad_request(detail: str, *, reason: str) -> ComposeError:
    return ComposeError(detail, reason=reason, status_code=400)


@dataclass(frozen=True, slots=True)
class DraftResult:
    """Step 1's answer: what would be stored, and how it differs."""

    draft_id: str
    room: str
    room_classes: tuple[str, ...]
    raw_text: str
    swept_text: str
    changed_by_sweep: bool
    raw_chars: int
    swept_chars: int
    draft_digest: str
    #: The live limits this text was measured against.
    min_chars: int
    max_chars: int
    expires_in_seconds: int
    #: Facts about the target the user should see before publishing.
    target_notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SignResult:
    """Step 2's answer: the exact bytes, signed, awaiting a send approval."""

    draft_id: str
    room: str
    did: str
    nonce: str
    canonical: str
    canonical_digest: str
    signature: str
    changed_by_sweep: bool
    send_token: str
    expires_in_seconds: int


@dataclass(frozen=True, slots=True)
class SendResult:
    """Step 3's answer. Three-valued, and never collapsed to two."""

    outcome: WriteOutcome
    room: str
    did: str
    nonce: str
    canonical_digest: str
    signature: str
    http_status: int
    detail: str
    response_excerpt: str
    #: True only for ``outcome_unknown``: the server may have written.
    reconciliation_required: bool


class ComposeService:
    """Owns the approval chain. The only caller of the write client."""

    def __init__(
        self,
        *,
        identity: ComposeIdentity,
        technocore: TechnocoreService,
        reserver: NonceReserver,
        signer: MessageSigner,
        write_client: SignedWriteClient,
        drafts: DraftStore | None = None,
        approvals: SingleUseStore[SendApproval] | None = None,
    ) -> None:
        self._identity = identity
        self._technocore = technocore
        self._reserver = reserver
        self._signer = signer
        self._write_client = write_client
        self._drafts = drafts if drafts is not None else DraftStore()
        self._approvals: SingleUseStore[SendApproval] = (
            approvals
            if approvals is not None
            else SingleUseStore(ttl_seconds=SEND_TOKEN_TTL_SECONDS)
        )

    # --- step 1: draft -----------------------------------------------------

    def draft(self, *, session_id: str, room: str, text: str) -> DraftResult:
        """Sweep and bind. Reserves no nonce and signs nothing."""
        status = self._require_open_gate()
        target = self._resolve_target(room, status)
        limits = self._payload_limits(status)
        swept = self._sweep(text, limits)

        record = self._drafts.put(
            session_id=session_id,
            room=target.room,
            raw_text=text,
            swept_text=swept,
            changed_by_sweep=swept != text,
        )

        return DraftResult(
            draft_id=record.id,
            room=target.room,
            room_classes=target.classes,
            raw_text=text,
            swept_text=swept,
            changed_by_sweep=record.changed_by_sweep,
            raw_chars=len(text),
            swept_chars=len(swept),
            draft_digest=record.digest,
            min_chars=limits.minimum,
            max_chars=limits.maximum,
            expires_in_seconds=self._drafts.ttl_seconds,
            target_notes=_target_notes(target),
        )

    # --- step 2: sign ------------------------------------------------------

    def sign(
        self,
        *,
        session_id: str,
        draft_id: str,
        confirmed_digest: str,
        vault_passphrase: str | None,
    ) -> SignResult:
        """Reserve, canonicalise, sign, and mint one send approval.

        The nonce is reserved *before* the signature, inside its own
        transaction, because the nonce is part of the bytes being signed.
        Everything after the reservation is wrapped so that a failure
        releases nothing back into circulation but does mark the number as
        spent-and-not-sent rather than leaving it dangling.

        The vault passphrase is registered with the log redactor for exactly
        this call. No leak path is known today - the product's own exceptions
        do not put it in their message, and a CPython traceback does not print
        locals - but the registry exists for values that travel through a call
        stack, and this is the only such value the composer handles. Relying on
        "no formatter renders it today" is relying on a property nobody
        maintains (SI-162).
        """
        if vault_passphrase is not None:
            register_secret(vault_passphrase)
        try:
            return self._sign(
                session_id=session_id,
                draft_id=draft_id,
                confirmed_digest=confirmed_digest,
                vault_passphrase=vault_passphrase,
            )
        finally:
            if vault_passphrase is not None:
                forget_secret(vault_passphrase)

    def _sign(
        self,
        *,
        session_id: str,
        draft_id: str,
        confirmed_digest: str,
        vault_passphrase: str | None,
    ) -> SignResult:
        status = self._require_open_gate()
        record = self._require_draft(draft_id, session_id=session_id)

        # The content the user approved has to be the content we are about to
        # sign. A re-sweep protects against the draft store and the digest
        # disagreeing; the digest comparison protects against the *client*
        # having shown something else.
        if confirmed_digest != record.digest:
            raise _approval_rejected(
                "Onaylanan icerik degismis. Metni veya hedef odayi "
                "degistirdiyseniz yeni bir taslak hazirlayin.",
                reason="draft_digest_mismatch",
            )
        if draft_digest(room=record.room, swept_text=record.swept_text) != record.digest:
            raise _approval_rejected(  # pragma: no cover - store integrity guard
                "Taslak butunlugu dogrulanamadi.", reason="draft_corrupt"
            )

        target = self._resolve_target(record.room, status)
        limits = self._payload_limits(status)
        self._check_length(record.swept_text, limits)

        signing = self._signing_identity()
        reservation = self._reserve(did=signing.did, room=target.room)

        try:
            payload = canonical_message(
                room=target.room, nonce=reservation.nonce, text=record.swept_text
            )
            # The sweep is idempotent, so building from already-swept text
            # must not change it. If it did, the bytes shown to the user and
            # the bytes signed would differ - the exact failure this chain
            # exists to prevent.
            if payload.swept_text != record.swept_text:
                raise _bad_request(  # pragma: no cover - idempotence guard
                    "Swept metin kararli degil; imzalanmadi.",
                    reason="sweep_not_idempotent",
                )

            signature = self._sign_payload(
                payload, identity_id=signing.identity_id, passphrase=vault_passphrase
            )
            self._verify_own_signature(payload, did=signing.did, signature=signature)
        except BaseException:
            # Nothing was sent. The number is still burnt - the counter is
            # strictly increasing - but the record says so honestly.
            self._reserver.cancel(reservation.id, detail="imzalama basarisiz")
            raise

        approval = SendApproval(
            draft_id=record.id,
            session_id=session_id,
            did=signing.did,
            room=target.room,
            nonce=reservation.nonce,
            reservation_id=reservation.id,
            canonical_digest=canonical_digest(payload.canonical_bytes),
            signature=signature,
            swept_text=record.swept_text,
            verdict_id=status.verdict_id,
        )
        token = self._approvals.issue(approval)

        return SignResult(
            draft_id=record.id,
            room=target.room,
            did=signing.did,
            nonce=reservation.nonce,
            canonical=payload.canonical,
            canonical_digest=approval.canonical_digest,
            signature=signature,
            changed_by_sweep=record.changed_by_sweep,
            send_token=token,
            expires_in_seconds=self._approvals.ttl_seconds,
        )

    # --- step 3: send ------------------------------------------------------

    def send(self, *, session_id: str, send_token: str) -> SendResult:
        """Spend one approval and POST once.

        The token is consumed first and atomically, so a double click loses
        the race rather than sending twice. Spending it costs the nonce
        whatever happens next, which is the point: an approval that has been
        acted on is gone even if the act failed.
        """
        accepted, approval = self._approvals.consume(send_token)
        if not accepted or approval is None:
            raise _approval_rejected(
                "Gonderim onayi gecersiz: kullanilmis, suresi dolmus veya hic "
                "verilmemis. Yeni bir imza onayi alin.",
                reason="approval_invalid",
            )

        if approval.session_id != session_id:
            self._reserver.cancel(
                approval.reservation_id, detail="onay baska oturuma ait"
            )
            raise _approval_rejected(
                "Bu onay baska bir oturuma ait.", reason="approval_foreign_session"
            )

        try:
            status = self._require_open_gate()
        except ComposeError:
            self._reserver.cancel(approval.reservation_id, detail="gate kapali")
            raise

        # Stale verdict: the protocol check that backed this approval is no
        # longer the current one. Re-running the check is new evidence, and
        # the user approved against the old evidence.
        if not approval.verdict_id or approval.verdict_id != status.verdict_id:
            self._reserver.cancel(approval.reservation_id, detail="verdict degisti")
            raise _approval_rejected(
                "Protokol denetimi bu onaydan sonra degisti. Guncel denetimi "
                "gorup yeniden onaylayin.",
                reason="stale_verdict",
            )

        signing = self._signing_identity_or_cancel(approval)
        if signing.did != approval.did:
            self._reserver.cancel(approval.reservation_id, detail="kimlik degisti")
            raise _approval_rejected(
                "Imzalayan kimlik degismis; bu onay artik gecerli degil.",
                reason="identity_changed",
            )

        target = self._resolve_target_or_cancel(approval, status)
        body = self._build_body_or_cancel(approval, status)

        # Spending starts here, in the same step as the send and before it:
        # a crash, a killed process or a lost response must leave the nonce
        # burnt rather than reusable.
        try:
            self._reserver.commit_to_send(approval.reservation_id)
        except NonceStorageError as exc:
            # The counter's database, not the counter's rules. Separated so the
            # UI does not tell a user their nonce was already spent when the
            # truth is that a second process is holding the file.
            raise _approval_rejected(
                str(exc), reason="nonce_storage_unavailable"
            ) from exc
        except NonceReservationError as exc:
            raise _approval_rejected(str(exc), reason="nonce_already_spent") from exc

        result = self._write_client.send(target, body)
        self._reserver.record_outcome(
            approval.reservation_id,
            outcome=WriteOutcomeValue(result.outcome.value),
            detail=result.detail,
        )

        return SendResult(
            outcome=result.outcome,
            room=approval.room,
            did=approval.did,
            nonce=approval.nonce,
            canonical_digest=approval.canonical_digest,
            signature=approval.signature,
            http_status=result.http_status,
            detail=_send_detail(result),
            response_excerpt=result.response_excerpt,
            reconciliation_required=result.outcome is WriteOutcome.OUTCOME_UNKNOWN,
        )

    # --- lifecycle ---------------------------------------------------------

    def forget_identity(self, did: str) -> None:
        """Drop every pending approval signed by a DID that is going away.

        Called when an identity is revoked. Not load-bearing on its own - a
        revoked identity closes the gate, and ``send`` re-runs the gate and
        re-compares the DID, so a stale approval would be refused twice over.
        It is here because leaving a live capability lying around until its
        TTL expires, for a key the user has just destroyed, is the wrong
        default even when nothing can act on it.
        """
        self._approvals.discard_where(lambda approval: approval.did == did)

    def forget_session(self, session_id: str) -> None:
        """Drop every draft and approval a session left behind.

        An approval outliving the session that produced it would be a
        capability with no owner. Sessions live only in process memory today,
        so this fires on an explicit revocation rather than on a browser tab
        closing; the send-time session binding is what actually enforces the
        property in between.
        """
        self._drafts.discard_session(session_id)
        self._approvals.discard_where(
            lambda approval: approval.session_id == session_id
        )

    # --- shared checks -----------------------------------------------------

    def _require_open_gate(self) -> TechnocoreStatus:
        """Re-run every precondition. Called by all three steps."""
        gate = self._identity.write_gate_status()
        if not gate.allowed:
            raise _gate_closed(
                "Yazma kapisi kapali: "
                + ", ".join(gate.blocking_reasons)
                + ". Once bu adimlari tamamlayin."
            )
        status = self._technocore.status()
        if not status.manifest_current:
            # Belt and braces: the gate above already consumes this fact, and
            # the two reading it separately means neither can be the only
            # thing standing between an approval and a live room.
            raise _gate_closed(
                "Resmi protokol denetimi guncel degil; gonderim yapilmaz."
            )
        return status

    def _resolve_target(self, room: str, status: TechnocoreStatus) -> WriteTarget:
        try:
            return resolve_message_target(
                room, markers=frozenset(status.room_class_markers)
            )
        except RoomPolicyError as exc:
            raise _bad_request(str(exc), reason="room_refused") from exc

    def _resolve_target_or_cancel(
        self, approval: SendApproval, status: TechnocoreStatus
    ) -> WriteTarget:
        try:
            return self._resolve_target(approval.room, status)
        except ComposeError:
            self._reserver.cancel(approval.reservation_id, detail="hedef reddedildi")
            raise

    def _payload_limits(self, status: TechnocoreStatus) -> SentLength:
        """The limits to enforce, read from the live check, never hardcoded.

        ``effective_payload_limits`` is the published bound intersected with
        the charter ceiling (charter 14.4), which is exactly what Package B
        exported it for.
        """
        projection = status.projection
        if projection is None:  # pragma: no cover - guarded by the gate
            raise _gate_closed("Etkin limitler okunamadi; gonderim yapilmaz.")
        return projection.effective_payload_limits[PAYLOAD_FIELD]

    def _sweep(self, text: str, limits: SentLength) -> str:
        try:
            swept = sweep(text, MESSAGE_POLICY)
        except SweepError as exc:
            raise _bad_request(
                "Metin gonderilemez: supurmeden sonra gorunur bir icerik "
                "kalmiyor veya protokol sinirini asiyor.",
                reason="text_rejected",
            ) from exc
        self._check_length(swept, limits)
        return swept

    def _check_length(self, swept: str, limits: SentLength) -> None:
        """Enforce the *effective* limits on the swept text.

        The sweep already applies the charter's own 4096 ceiling. This is the
        second half: a live service publishing a tighter bound is honoured
        here rather than discovered as a 400 from the server.
        """
        if len(swept) < limits.minimum:
            raise _bad_request(
                f"Metin en az {limits.minimum} karakter olmali.",
                reason="text_too_short",
            )
        if len(swept) > limits.maximum:
            raise _bad_request(
                f"Metin en fazla {limits.maximum} karakter olabilir; supurmeden "
                f"sonra {len(swept)} karakter.",
                reason="text_too_long",
            )

    def _require_draft(self, draft_id: str, *, session_id: str) -> Draft:
        record = self._drafts.get(draft_id, session_id=session_id)
        if record is None:
            raise _approval_rejected(
                "Taslak bulunamadi veya suresi doldu. Yeniden hazirlayin.",
                reason="draft_missing",
            )
        return record

    def _signing_identity(self) -> SigningIdentity:
        try:
            return self._identity.active_signing_identity()
        except IdentityServiceError as exc:
            raise _gate_closed(str(exc)) from exc

    def _signing_identity_or_cancel(self, approval: SendApproval) -> SigningIdentity:
        try:
            return self._signing_identity()
        except ComposeError:
            self._reserver.cancel(approval.reservation_id, detail="kimlik yok")
            raise

    def _reserve(self, *, did: str, room: str) -> NonceReservation:
        try:
            return self._reserver.reserve(did=did, room=room)
        except NonceReservationError as exc:
            raise ComposeError(
                str(exc), reason="nonce_unavailable", status_code=409
            ) from exc

    def _sign_payload(
        self, payload: CanonicalPayload, *, identity_id: str, passphrase: str | None
    ) -> str:
        try:
            return self._signer.sign(
                payload, identity_id=identity_id, passphrase=passphrase
            )
        except VaultUnlockError as exc:
            raise _bad_request(
                "Kasa acilamadi. Parolayi kontrol edin.", reason="vault_locked"
            ) from exc
        except VaultError as exc:
            raise _gate_closed("Secret kasasi kullanilabilir degil.") from exc
        except ConformanceError as exc:  # pragma: no cover - payload is built here
            raise _bad_request(
                "Imza uretilemedi.", reason="signature_failed"
            ) from exc

    def _verify_own_signature(
        self, payload: CanonicalPayload, *, did: str, signature: str
    ) -> None:
        """Verify what we just produced, against the DID we will send.

        Not defensive theatre. The signature travels in a body the server
        checks against the *stored* bytes, and a mismatch there is a 403 with
        no explanation. Verifying locally turns a signing-path bug into a
        refusal here, before anything is published, and it is a real
        verification rather than a length check - the 86-character shape is
        necessary and nowhere near sufficient.
        """
        if not is_canonical_signature(signature):
            raise _bad_request(  # pragma: no cover - encoder guarantees the shape
                "Uretilen imza kanonik bicimde degil.", reason="signature_malformed"
            )
        try:
            verify_payload(payload, did=did, signature=signature)
        except ConformanceError as exc:
            raise _bad_request(
                "Uretilen imza kendi kanonik metnimizi dogrulamiyor; "
                "gonderilmedi.",
                reason="signature_invalid",
            ) from exc

    def _build_body_or_cancel(
        self, approval: SendApproval, status: TechnocoreStatus
    ) -> dict[str, str]:
        """Settle the reservation on the last refusal path in ``send``.

        Not a reuse hole either way - the number stays burnt, because a
        reservation is never returned to circulation - but every other refusal
        in ``send`` records *why* it ended, and one that did not left the row
        sitting at ``reserved`` for a request that provably stopped. A ledger
        with one silent exit is a ledger a reader cannot trust.
        """
        try:
            return self._build_body(approval, status)
        except ComposeError:
            self._reserver.cancel(approval.reservation_id, detail="govde dogrulanamadi")
            raise

    def _build_body(
        self, approval: SendApproval, status: TechnocoreStatus
    ) -> dict[str, str]:
        """Rebuild and re-validate the request body at send time.

        Everything here is checked again rather than trusted from the
        approval, because the approval is three minutes old and the point of
        the exercise is that nothing in between is assumed. The canonical
        bytes are rebuilt from the approved fields and compared against the
        digest the signature was taken over, so a body that drifted from the
        signed bytes cannot leave.
        """
        limits = self._payload_limits(status)
        self._check_length(approval.swept_text, limits)

        if not is_swept(approval.swept_text, MESSAGE_POLICY):
            raise _bad_request(  # pragma: no cover - swept on the way in
                "Gonderilecek metin supurulmus bicimde degil.",
                reason="text_not_swept",
            )

        payload = canonical_message(
            room=approval.room, nonce=approval.nonce, text=approval.swept_text
        )
        if canonical_digest(payload.canonical_bytes) != approval.canonical_digest:
            raise _approval_rejected(
                "Gonderilecek baytlar imzalanan baytlarla ayni degil.",
                reason="canonical_mismatch",
            )
        self._verify_own_signature(
            payload, did=approval.did, signature=approval.signature
        )

        body = {
            "did": approval.did,
            "sig": approval.signature,
            "nonce": approval.nonce,
            PAYLOAD_FIELD: approval.swept_text,
        }
        # The field set is taken from the projection, so a change to what the
        # signed lane requires shows up here as a failure rather than as a
        # silently wrong request.
        if set(body) != set(MESSAGE_BODY_FIELDS):
            raise _bad_request(  # pragma: no cover - both sides are constants
                "Istek govdesi planlanan alan kumesiyle uyusmuyor.",
                reason="body_fields_mismatch",
            )
        if any(not isinstance(value, str) or not value for value in body.values()):
            raise _bad_request(  # pragma: no cover - all four are built above
                "Istek govdesinde bos veya metin olmayan alan var.",
                reason="body_field_invalid",
            )
        return body


def _target_notes(target: WriteTarget) -> tuple[str, ...]:
    """Facts about the room that change what publishing there means."""
    notes: list[str] = []
    if target.is_ephemeral:
        notes.append(
            "Bu oda gecicidir: mesajlar okuma aninda suresi dolmus sayilabilir, "
            "yani kanit kalici olmayabilir."
        )
    if target.is_unlisted:
        notes.append(
            "Bu oda listelenmez; adi bilen herkes okuyabilir. Ad bir sirdir, "
            "erisim denetimi degildir."
        )
    if target.is_ownable:
        notes.append(
            "Bu oda sahiplenilebilir siniftadir; sahibi yazmayi kisitlamissa "
            "sunucu istegi reddedebilir."
        )
    if target.is_mailbox:
        notes.append("Bu oda yalniz imzali yazma kabul eder.")
    return tuple(notes)


def _send_detail(result: WriteResult) -> str:
    """The sentence the user reads, with the honest caveat attached."""
    if result.outcome is WriteOutcome.OUTCOME_UNKNOWN:
        return (
            f"{result.detail} Bu islem 'gonderildi' veya 'basarisiz' olarak "
            "sunulamaz; nonce harcanmistir ve yeniden denemek yeni bir nonce "
            "ve yeni bir onay gerektirir."
        )
    return result.detail


__all__ = [
    "MESSAGE_BODY_FIELDS",
    "PAYLOAD_FIELD",
    "ComposeError",
    "ComposeIdentity",
    "ComposeService",
    "DraftResult",
    "SendResult",
    "SignResult",
]
