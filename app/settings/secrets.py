"""Secret storage backed by Windows Credential Manager."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Protocol


class SecretStore(Protocol):
    def get(self, name: str) -> str | None: ...

    def set(self, name: str, value: str) -> None: ...

    def delete(self, name: str) -> None: ...


class UnavailableSecretStore:
    """Read-only fallback for non-Windows development environments."""

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None:
        raise RuntimeError("系统凭据存储仅在 Windows 打包版中可用")

    def delete(self, name: str) -> None:
        return None


if sys.platform == "win32":
    LPBYTE = ctypes.POINTER(wintypes.BYTE)

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", LPBYTE),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", wintypes.LPVOID),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


class WindowsCredentialStore:
    """Store secrets as generic credentials for the current Windows user."""

    _TYPE_GENERIC = 1
    _PERSIST_LOCAL_MACHINE = 2
    _ERROR_NOT_FOUND = 1168
    _PREFIX = "HyperAgent/"

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows Credential Manager is unavailable")
        self._advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self._advapi32.CredWriteW.argtypes = [PCREDENTIALW, wintypes.DWORD]
        self._advapi32.CredWriteW.restype = wintypes.BOOL
        self._advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(PCREDENTIALW),
        ]
        self._advapi32.CredReadW.restype = wintypes.BOOL
        self._advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self._advapi32.CredDeleteW.restype = wintypes.BOOL
        self._advapi32.CredFree.argtypes = [wintypes.LPVOID]
        self._advapi32.CredFree.restype = None

    def _target(self, name: str) -> str:
        return f"{self._PREFIX}{name}"

    def get(self, name: str) -> str | None:
        credential_ptr = PCREDENTIALW()
        ok = self._advapi32.CredReadW(
            self._target(name), self._TYPE_GENERIC, 0, ctypes.byref(credential_ptr)
        )
        if not ok:
            error = ctypes.get_last_error()
            if error == self._ERROR_NOT_FOUND:
                return None
            raise ctypes.WinError(error)
        try:
            credential = credential_ptr.contents
            raw = ctypes.string_at(
                credential.CredentialBlob, credential.CredentialBlobSize
            )
            return raw.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(credential_ptr)

    def set(self, name: str, value: str) -> None:
        raw = value.encode("utf-16-le")
        blob = (wintypes.BYTE * len(raw)).from_buffer_copy(raw)
        credential = CREDENTIALW()
        credential.Type = self._TYPE_GENERIC
        credential.TargetName = self._target(name)
        credential.CredentialBlobSize = len(raw)
        credential.CredentialBlob = ctypes.cast(blob, LPBYTE)
        credential.Persist = self._PERSIST_LOCAL_MACHINE
        credential.UserName = "HyperAgent"
        if not self._advapi32.CredWriteW(ctypes.byref(credential), 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def delete(self, name: str) -> None:
        ok = self._advapi32.CredDeleteW(
            self._target(name), self._TYPE_GENERIC, 0
        )
        if not ok:
            error = ctypes.get_last_error()
            if error != self._ERROR_NOT_FOUND:
                raise ctypes.WinError(error)


def create_secret_store() -> SecretStore:
    if sys.platform == "win32":
        return WindowsCredentialStore()
    return UnavailableSecretStore()
