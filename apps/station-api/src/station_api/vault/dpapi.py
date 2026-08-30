"""Windows DPAPI protect/unprotect, current-user scope only.

``CRYPTPROTECT_LOCAL_MACHINE`` is deliberately never passed. Machine scope
would let *any* account on the computer unprotect the blob, which defeats the
point: the vault is bound to this Windows user.

Additional entropy is supplied, but it is a fixed application constant
compiled into the source. It is **not a secret** and adds no confidentiality
against anyone who can read this file. It only domain-separates our blobs
from other DPAPI data belonging to the same user.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Any

from station_api.vault.errors import (
    VaultCapabilityError,
    VaultUnlockError,
    VaultUnsupportedPlatformError,
)

#: Fixed, public domain-separation constant. NOT a secret (see module docstring).
DPAPI_ENTROPY = b"technocore-station/vault/v1"

#: Never let DPAPI raise a UI prompt that could hang a headless process.
_CRYPTPROTECT_UI_FORBIDDEN = 0x01

#: Present only to document what is intentionally NOT used. Setting this would
#: widen the blob to every account on the machine.
_CRYPTPROTECT_LOCAL_MACHINE = 0x04


class _DataBlob(ctypes.Structure):
    _fields_ = (
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    )


def is_supported() -> bool:
    return sys.platform == "win32"


def _crypt32() -> Any:
    return ctypes.WinDLL("crypt32", use_last_error=True)


def _kernel32() -> Any:
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _blob_in(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer  # buffer returned so the caller keeps it alive


def _blob_out_bytes(blob: _DataBlob) -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32().LocalFree(blob.pbData)


def _require_windows() -> None:
    if not is_supported():
        raise VaultUnsupportedPlatformError(
            "Windows DPAPI is required. This platform has no supported secret store."
        )


def protect(plaintext: bytes) -> bytes:
    """DPAPI-protect bytes for the **current user**."""
    _require_windows()

    crypt32 = _crypt32()
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    data_in, _keep_data = _blob_in(plaintext)
    entropy_in, _keep_entropy = _blob_in(DPAPI_ENTROPY)
    data_out = _DataBlob()

    ok = crypt32.CryptProtectData(
        ctypes.byref(data_in),
        None,  # no description: it would be stored in cleartext beside the blob
        ctypes.byref(entropy_in),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,  # current-user scope: LOCAL_MACHINE not set
        ctypes.byref(data_out),
    )
    if not ok:
        raise VaultCapabilityError("DPAPI could not protect the payload")

    return _blob_out_bytes(data_out)


def unprotect(ciphertext: bytes) -> bytes:
    """DPAPI-unprotect bytes previously protected for this user."""
    _require_windows()

    crypt32 = _crypt32()
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    data_in, _keep_data = _blob_in(ciphertext)
    entropy_in, _keep_entropy = _blob_in(DPAPI_ENTROPY)
    data_out = _DataBlob()

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(data_in),
        None,
        ctypes.byref(entropy_in),
        None,
        None,
        _CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(data_out),
    )
    if not ok:
        # Same error as a wrong passphrase: the caller learns only that the
        # secret could not be opened.
        raise VaultUnlockError("DPAPI could not unprotect the payload")

    return _blob_out_bytes(data_out)


def self_test() -> bool:
    """Prove DPAPI works here before an identity depends on it.

    Runs at startup so a broken environment surfaces as a capability error
    rather than as a lost seed later.
    """
    if not is_supported():
        return False
    probe = b"technocore-station-dpapi-self-test"
    try:
        return unprotect(protect(probe)) == probe
    except (VaultCapabilityError, VaultUnlockError, OSError):
        return False


__all__ = ["DPAPI_ENTROPY", "is_supported", "protect", "self_test", "unprotect"]
