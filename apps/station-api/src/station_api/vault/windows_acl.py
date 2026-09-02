"""Restrictive Windows ACLs applied through the Windows API.

The vault file must be readable only by the current user and by SYSTEM. This
module builds that DACL with ``advapi32`` directly rather than shelling out to
``icacls``: a shell invocation is an injection surface, its failures are easy
to miss, and it cannot be verified in-process.

The DACL is written **protected** (``D:P``), which strips inherited entries
from the parent directory - otherwise a permissive ``%LOCALAPPDATA%`` ACE
would still grant access.

Every failure raises ``VaultAclError``; nothing here degrades silently.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

from station_api.vault.errors import VaultAclError

#: SDDL: protected DACL granting full access to SYSTEM and the current user.
_SDDL_TEMPLATE = "D:P(A;;FA;;;SY)(A;;FA;;;{sid})"

_SDDL_REVISION_1 = 1
_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_TOKEN_QUERY = 0x0008
_TOKEN_USER_CLASS = 1
_ERROR_SUCCESS = 0


def is_windows() -> bool:
    return sys.platform == "win32"


def _advapi32() -> Any:
    return ctypes.WinDLL("advapi32", use_last_error=True)


def _kernel32() -> Any:
    return ctypes.WinDLL("kernel32", use_last_error=True)


def current_user_sid() -> str:
    """Return the current process user's SID in string form (S-1-5-21-...)."""
    if not is_windows():  # pragma: no cover - guarded by callers
        raise VaultAclError("windows acl support is unavailable on this platform")

    advapi32 = _advapi32()
    kernel32 = _kernel32()

    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL

    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), _TOKEN_QUERY, ctypes.byref(token)
    ):
        raise VaultAclError("could not open the process token to read the user SID")

    try:
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL

        size = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(size))
        if size.value == 0:
            raise VaultAclError("could not size the token user information")

        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, _TOKEN_USER_CLASS, buffer, size, ctypes.byref(size)
        ):
            raise VaultAclError("could not read the token user information")

        # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first member is PSID.
        sid_pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents

        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

        sid_string = ctypes.c_wchar_p()
        if not advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(sid_string)):
            raise VaultAclError("could not convert the user SID to string form")
        try:
            value = sid_string.value
            if not value:
                raise VaultAclError("empty user SID")
            return value
        finally:
            kernel32.LocalFree(sid_string)
    finally:
        kernel32.CloseHandle(token)


def _dacl_from_sddl(sddl: str) -> tuple[Any, Any]:
    """Parse an SDDL string and return (security_descriptor, dacl_pointer)."""
    advapi32 = _advapi32()
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.ULONG),
    ]
    advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL

    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl, _SDDL_REVISION_1, ctypes.byref(descriptor), None
    ):
        raise VaultAclError("could not build the security descriptor")

    advapi32.GetSecurityDescriptorDacl.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.BOOL),
    ]
    advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL

    present = wintypes.BOOL()
    dacl = ctypes.c_void_p()
    defaulted = wintypes.BOOL()
    if not advapi32.GetSecurityDescriptorDacl(
        descriptor, ctypes.byref(present), ctypes.byref(dacl), ctypes.byref(defaulted)
    ):
        _kernel32().LocalFree(descriptor)
        raise VaultAclError("could not read the DACL from the security descriptor")

    return descriptor, dacl


def restrict_to_current_user(path: Path) -> str:
    """Apply a protected DACL granting only the current user and SYSTEM.

    Returns the SDDL that was applied. Raises ``VaultAclError`` on any failure -
    a vault whose ACL could not be set must not be treated as protected.
    """
    if not is_windows():
        raise VaultAclError("windows acl support is unavailable on this platform")
    if not path.exists():
        raise VaultAclError("cannot apply an ACL to a path that does not exist")

    sddl = _SDDL_TEMPLATE.format(sid=current_user_sid())
    descriptor, dacl = _dacl_from_sddl(sddl)

    try:
        advapi32 = _advapi32()
        advapi32.SetNamedSecurityInfoW.argtypes = [
            wintypes.LPWSTR,
            ctypes.c_int,
            wintypes.DWORD,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD

        name = ctypes.create_unicode_buffer(str(path))
        result = advapi32.SetNamedSecurityInfoW(
            name,
            _SE_FILE_OBJECT,
            _DACL_SECURITY_INFORMATION | _PROTECTED_DACL_SECURITY_INFORMATION,
            None,
            None,
            dacl,
            None,
        )
        if result != _ERROR_SUCCESS:
            raise VaultAclError(f"could not apply the vault ACL (win32 error {result})")
    finally:
        _kernel32().LocalFree(descriptor)

    return sddl


def describe_acl(path: Path) -> str:
    """Read back the DACL as an SDDL string, for verification and tests."""
    if not is_windows():
        raise VaultAclError("windows acl support is unavailable on this platform")

    advapi32 = _advapi32()
    kernel32 = _kernel32()

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD

    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != _ERROR_SUCCESS:
        raise VaultAclError(f"could not read the vault ACL (win32 error {result})")

    try:
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_wchar_p),
            ctypes.POINTER(wintypes.ULONG),
        ]
        advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW.restype = wintypes.BOOL

        text = ctypes.c_wchar_p()
        if not advapi32.ConvertSecurityDescriptorToStringSecurityDescriptorW(
            descriptor, _SDDL_REVISION_1, _DACL_SECURITY_INFORMATION, ctypes.byref(text), None
        ):
            raise VaultAclError("could not render the vault ACL as SDDL")
        try:
            return text.value or ""
        finally:
            kernel32.LocalFree(text)
    finally:
        kernel32.LocalFree(descriptor)


_ACCESS_ALLOWED_ACE_TYPE = 0
#: Offset of SidStart inside ACCESS_ALLOWED_ACE: ACE_HEADER (4 bytes) + Mask.
_SID_START_OFFSET = 8


class _AclSizeInformation(ctypes.Structure):
    _fields_ = [
        ("AceCount", wintypes.DWORD),
        ("AclBytesInUse", wintypes.DWORD),
        ("AclBytesFree", wintypes.DWORD),
    ]


def acl_grantee_sids(path: Path) -> tuple[str, ...]:
    """The actual SIDs the file's DACL grants access to, in string form.

    SDDL abbreviates well-known principals - the built-in Administrator
    renders as ``LA``, not as its ``S-1-5-21-...-500`` string - so substring
    checks against :func:`describe_acl` output are account-dependent. This
    walks the real ACEs and converts each trustee SID directly, which makes
    "exactly SYSTEM and the current user" checkable as SID equality on any
    account. Only ACCESS_ALLOWED entries are returned; any other ACE type in
    a vault DACL is unexpected and raises.
    """
    if not is_windows():
        raise VaultAclError("windows acl support is unavailable on this platform")

    advapi32 = _advapi32()
    kernel32 = _kernel32()

    advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD

    dacl = ctypes.c_void_p()
    descriptor = ctypes.c_void_p()
    result = advapi32.GetNamedSecurityInfoW(
        str(path),
        _SE_FILE_OBJECT,
        _DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(dacl),
        None,
        ctypes.byref(descriptor),
    )
    if result != _ERROR_SUCCESS:
        raise VaultAclError(f"could not read the vault ACL (win32 error {result})")

    try:
        if not dacl:
            raise VaultAclError("the vault has no DACL to inspect")

        advapi32.GetAclInformation.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_int,
        ]
        advapi32.GetAclInformation.restype = wintypes.BOOL
        info = _AclSizeInformation()
        # 2 = AclSizeInformation
        if not advapi32.GetAclInformation(
            dacl, ctypes.byref(info), ctypes.sizeof(info), 2
        ):
            raise VaultAclError("could not size the vault DACL")

        advapi32.GetAce.argtypes = [
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        advapi32.GetAce.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]
        advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL

        sids: list[str] = []
        for index in range(info.AceCount):
            ace = ctypes.c_void_p()
            if not advapi32.GetAce(dacl, index, ctypes.byref(ace)):
                raise VaultAclError(f"could not read vault ACE {index}")
            ace_type = ctypes.cast(ace, ctypes.POINTER(ctypes.c_ubyte))[0]
            if ace_type != _ACCESS_ALLOWED_ACE_TYPE:
                raise VaultAclError(
                    f"unexpected ACE type {ace_type} in the vault DACL"
                )
            sid_pointer = ctypes.c_void_p((ace.value or 0) + _SID_START_OFFSET)
            text = ctypes.c_wchar_p()
            if not advapi32.ConvertSidToStringSidW(sid_pointer, ctypes.byref(text)):
                raise VaultAclError(f"could not convert the SID of vault ACE {index}")
            try:
                if not text.value:
                    raise VaultAclError(f"empty SID on vault ACE {index}")
                sids.append(text.value)
            finally:
                kernel32.LocalFree(text)
        return tuple(sids)
    finally:
        kernel32.LocalFree(descriptor)


__all__ = [
    "acl_grantee_sids",
    "current_user_sid",
    "describe_acl",
    "is_windows",
    "restrict_to_current_user",
]
