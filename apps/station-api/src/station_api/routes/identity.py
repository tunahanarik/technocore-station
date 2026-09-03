"""Identity and recovery endpoints.

Every route here is session-protected, and every state-changing route also
passes the existing CSRF, Host, Origin and Sec-Fetch-Site guards - they are
applied globally as middleware, so nothing in this file can opt out.

What is deliberately absent:

* There is **no raw-seed endpoint**. A seed can only enter this application
  through the local CLI, which reads a file path the user types at their own
  terminal. Accepting seed bytes over HTTP would put them in a request body,
  a proxy buffer and potentially a log.
* There is no endpoint that returns a seed, a private key or a vault path.

Uploads are capped and read into memory deliberately: a ``.tcrec`` is a few
hundred bytes, so a streaming path would add risk without value.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import Response
from technocore_conform import fingerprint_from_public_key, public_key_from_did_key
from technocore_conform import short_fingerprint as make_short_fingerprint

from station_api.dependencies import require_session
from station_api.identity.service import (
    IdentityService,
    IdentityServiceError,
    IdentityView,
)
from station_api.recovery import MAX_RECOVERY_BYTES, RECOVERY_FAILURE_MESSAGE, RECOVERY_SUFFIX
from station_api.schemas import (
    CREATE_IDENTITY_CONFIRMATION,
    CreateIdentityRequest,
    ExportRecoveryRequest,
    GateCheckStatus,
    IdentityPublic,
    IdentityStatusResponse,
    RecoveryInspectResponse,
    RecoveryStatus,
    RevokeIdentityRequest,
    VaultCapabilityStatus,
    WriteGateResponse,
)
from station_api.security.sessions import Session
from station_api.vault import DEFAULT_PROTECTION, ProtectionMode
from station_api.vault.errors import UNLOCK_FAILURE_MESSAGE, VaultError, VaultUnlockError
from station_api.vault.passphrase import (
    MIN_PASSPHRASE_CHARS,
    PassphrasePolicyError,
    validate_passphrase,
)

router = APIRouter(prefix="/api/identity")
gate_router = APIRouter(prefix="/api")

CurrentSession = Annotated[Session, Depends(require_session)]

#: Responses that carry recovery material or session-scoped state.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


def _service(request: Request) -> IdentityService:
    service: IdentityService | None = getattr(request.app.state, "identity_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Kimlik servisi kullanilabilir degil.",
        )
    return service


def _validate_passphrase(passphrase: str) -> None:
    try:
        validate_passphrase(passphrase)
    except PassphrasePolicyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _gate_response(view: IdentityView) -> WriteGateResponse:
    return WriteGateResponse(
        allowed=view.gate.allowed,
        identity_ready=view.gate.identity_ready,
        blocking_reasons=list(view.gate.blocking_reasons),
        checks=[
            GateCheckStatus(
                key=check.key,
                state=check.state.value,
                detail=check.detail,
                stage=check.stage,
            )
            for check in view.gate.checks
        ],
    )


def _to_response(view: IdentityView) -> IdentityStatusResponse:
    identity = None
    if view.did is not None and view.created_at is not None:
        identity = IdentityPublic(
            did=view.did,
            public_key=view.public_key or "",
            fingerprint=view.fingerprint or "",
            fingerprint_short=make_short_fingerprint(view.fingerprint or ""),
            label=view.label or "",
            status=str(view.state.value),
            protection=view.protection,
            created_at=view.created_at,
            revoked_at=view.revoked_at,
        )

    return IdentityStatusResponse(
        state=view.state.value,
        identity=identity,
        recovery=RecoveryStatus(
            exported_at=view.recovery.exported_at,
            verified_at=view.recovery.verified_at,
            file_fingerprint=view.recovery.file_fingerprint,
            kdf=view.recovery.kdf,
            kdf_time_cost=view.recovery.kdf_time_cost,
            kdf_memory_kib=view.recovery.kdf_memory_kib,
            kdf_parallelism=view.recovery.kdf_parallelism,
        ),
        capability=VaultCapabilityStatus(
            platform_supported=view.capability.platform_supported,
            dpapi_available=view.capability.dpapi_available,
            aead_available=view.capability.aead_available,
            usable=view.capability.usable,
            detail=view.capability.detail,
        ),
        gate=_gate_response(view),
        default_protection=DEFAULT_PROTECTION.value,
        min_passphrase_chars=MIN_PASSPHRASE_CHARS,
        create_confirmation_text=CREATE_IDENTITY_CONFIRMATION,
    )


def _json(
    model: IdentityStatusResponse | WriteGateResponse | RecoveryInspectResponse,
    *,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """Serialise a response model with no-store headers.

    Returning a Response directly bypasses the decorator's ``status_code``,
    so creating routes pass theirs explicitly.
    """
    return Response(
        content=model.model_dump_json(),
        media_type="application/json",
        status_code=status_code,
        headers=_NO_STORE,
    )


async def _read_recovery_upload(upload: UploadFile) -> bytes:
    """Read an uploaded ``.tcrec``, refusing anything over the cap.

    One byte past the limit is enough to reject: we never buffer the whole of
    an oversized upload.
    """
    payload = await upload.read(MAX_RECOVERY_BYTES + 1)
    if len(payload) > MAX_RECOVERY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Recovery dosyasi cok buyuk.",
        )
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Recovery dosyasi bos."
        )
    return payload


def _unlock_failure() -> HTTPException:
    """One status and one message for every failure to open protected data.

    Wrong passphrase, tampered ciphertext and tampered header are
    indistinguishable from outside. We do not claim timing equality.
    """
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=RECOVERY_FAILURE_MESSAGE,
        headers=_NO_STORE,
    )


# --- read ------------------------------------------------------------------


@router.get("", response_model=IdentityStatusResponse)
async def read_identity(request: Request, session: CurrentSession) -> Response:
    del session
    return _json(_to_response(_service(request).describe()))


@gate_router.get("/write-gate", response_model=WriteGateResponse)
async def read_write_gate(request: Request, session: CurrentSession) -> Response:
    del session
    return _json(_gate_response(_service(request).describe()))


# --- create ----------------------------------------------------------------


@router.post("", response_model=IdentityStatusResponse, status_code=status.HTTP_201_CREATED)
async def create_identity(
    request: Request, session: CurrentSession, body: CreateIdentityRequest
) -> Response:
    del session
    service = _service(request)

    if body.confirmation != CREATE_IDENTITY_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Onay metni tam olarak yazilmalidir.",
        )

    protection = ProtectionMode(body.protection)
    passphrase: str | None = None

    if protection is ProtectionMode.DPAPI_PASSPHRASE:
        if body.passphrase is None or body.passphrase_confirm is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Parola gerekli."
            )
        passphrase = body.passphrase.get_secret_value()
        if passphrase != body.passphrase_confirm.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Parolalar eslesmiyor."
            )
        _validate_passphrase(passphrase)
    elif not body.accept_dpapi_only_risk:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Parolasiz koruma icin risk onayi gerekli.",
        )

    try:
        view = service.create(protection=protection, passphrase=passphrase, label=body.label)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except VaultError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Secret kasasi kullanilabilir degil.",
        ) from exc

    return _json(_to_response(view), status_code=status.HTTP_201_CREATED)


# --- recovery export -------------------------------------------------------


@router.post("/recovery/export")
async def export_recovery(
    request: Request, session: CurrentSession, body: ExportRecoveryRequest
) -> Response:
    """Return the encrypted ``.tcrec`` as a download.

    The body is the ciphertext file itself and nothing else: no JSON wrapper
    that a proxy might log, and no seed.
    """
    del session
    service = _service(request)

    recovery_passphrase = body.recovery_passphrase.get_secret_value()
    if recovery_passphrase != body.recovery_passphrase_confirm.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Parolalar eslesmiyor."
        )
    _validate_passphrase(recovery_passphrase)

    vault_passphrase = (
        body.vault_passphrase.get_secret_value() if body.vault_passphrase else None
    )

    try:
        payload, did = service.export_recovery(
            recovery_passphrase=recovery_passphrase, vault_passphrase=vault_passphrase
        )
    except VaultUnlockError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=UNLOCK_FAILURE_MESSAGE,
            headers=_NO_STORE,
        ) from exc
    except IdentityServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    filename = f"technocore-station-{did[-12:]}{RECOVERY_SUFFIX}"
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={**_NO_STORE, "Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- restore test ----------------------------------------------------------


@router.post("/recovery/verify", response_model=IdentityStatusResponse)
async def verify_recovery(
    request: Request,
    session: CurrentSession,
    recovery_file: Annotated[UploadFile, File()],
    recovery_passphrase: Annotated[str, Form()],
) -> Response:
    """Restore-test: prove the file reconstructs the installed identity.

    Touches neither the vault nor the installed seed. On failure nothing at
    all changes.
    """
    del session
    service = _service(request)
    payload = await _read_recovery_upload(recovery_file)

    try:
        view = service.restore_test(payload=payload, recovery_passphrase=recovery_passphrase)
    except VaultUnlockError as exc:
        raise _unlock_failure() from exc
    except IdentityServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc), headers=_NO_STORE
        ) from exc

    return _json(_to_response(view))


# --- clean profile adoption ------------------------------------------------


@router.post("/recovery/inspect", response_model=RecoveryInspectResponse)
async def inspect_recovery(
    request: Request,
    session: CurrentSession,
    recovery_file: Annotated[UploadFile, File()],
    recovery_passphrase: Annotated[str, Form()],
) -> Response:
    """Show the public DID inside a recovery file, before adopting it.

    Writes nothing. This is what the user confirms against.
    """
    del session
    service = _service(request)
    payload = await _read_recovery_upload(recovery_file)

    try:
        did = service.inspect_recovery(
            payload=payload, recovery_passphrase=recovery_passphrase
        )
    except VaultUnlockError as exc:
        raise _unlock_failure() from exc

    fingerprint = fingerprint_from_public_key(public_key_from_did_key(did))
    return _json(
        RecoveryInspectResponse(
            did=did,
            fingerprint=fingerprint,
            fingerprint_short=make_short_fingerprint(fingerprint),
        )
    )


@router.post(
    "/recovery/adopt",
    response_model=IdentityStatusResponse,
    status_code=status.HTTP_201_CREATED,
)
async def adopt_recovery(
    request: Request,
    session: CurrentSession,
    recovery_file: Annotated[UploadFile, File()],
    recovery_passphrase: Annotated[str, Form()],
    protection: Annotated[str, Form()],
    confirm_did: Annotated[str, Form()],
    vault_passphrase: Annotated[str | None, Form()] = None,
    label: Annotated[str, Form()] = "",
) -> Response:
    """Install an identity on a clean profile from a ``.tcrec``."""
    del session
    service = _service(request)
    payload = await _read_recovery_upload(recovery_file)

    if protection not in {mode.value for mode in ProtectionMode}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Bilinmeyen koruma modu."
        )
    mode = ProtectionMode(protection)
    if mode is ProtectionMode.DPAPI_PASSPHRASE:
        if not vault_passphrase:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Kasa parolasi gerekli."
            )
        _validate_passphrase(vault_passphrase)

    try:
        # Confirm the user is adopting the identity they were shown.
        seen_did = service.inspect_recovery(
            payload=payload, recovery_passphrase=recovery_passphrase
        )
        if seen_did != confirm_did:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Onaylanan DID dosyadaki DID ile eslesmiyor.",
            )
        view = service.adopt_from_recovery(
            payload=payload,
            recovery_passphrase=recovery_passphrase,
            protection=mode,
            vault_passphrase=vault_passphrase,
            label=label,
        )
    except VaultUnlockError as exc:
        raise _unlock_failure() from exc
    except IdentityServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc), headers=_NO_STORE
        ) from exc

    return _json(_to_response(view), status_code=status.HTTP_201_CREATED)


# --- revoke ----------------------------------------------------------------


@router.post("/revoke", response_model=IdentityStatusResponse)
async def revoke_identity(
    request: Request, session: CurrentSession, body: RevokeIdentityRequest
) -> Response:
    del session
    service = _service(request)
    try:
        view = service.revoke(confirm_did=body.confirm_did)
    except IdentityServiceError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    # A pending send approval signed by a key the user has just destroyed
    # should not sit there until its TTL runs out. Nothing could act on it -
    # revocation closes the write gate, and the send step re-runs the gate
    # and re-compares the DID - but leaving a live capability behind for a
    # revoked identity is the wrong default even when it is inert.
    composer = getattr(request.app.state, "compose", None)
    if composer is not None:
        composer.forget_identity(body.confirm_did)

    return _json(_to_response(view))
