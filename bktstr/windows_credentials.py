"""Windows-only credential storage. No file or plaintext fallback."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import sys


def mutex_name(target: str, user_sid: bytes) -> str:
    """Match the vault's per-user, cross-session persistence boundary."""
    identity = user_sid + b"\0" + target.encode("utf-8")
    return "Global\\bktstr-credentials-" + hashlib.sha256(identity).hexdigest()


class _Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class WindowsCredentialStore:
    """One generic credential persisted for this Windows user on this computer."""

    def __init__(self, target: str):
        if sys.platform != "win32":
            raise OSError("Local credentials require Windows Credential Manager.")
        self.target = target
        self.api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        self.kernel = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
        pointer = ctypes.POINTER(_Credential)
        self.api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(pointer)]
        self.api.CredReadW.restype = wintypes.BOOL
        self.api.CredWriteW.argtypes = [pointer, wintypes.DWORD]
        self.api.CredWriteW.restype = wintypes.BOOL
        self.api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        self.api.CredDeleteW.restype = wintypes.BOOL
        self.api.CredFree.argtypes = [ctypes.c_void_p]
        self.api.CredFree.restype = None
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self.kernel.ReleaseMutex.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.GetCurrentProcess.argtypes = []
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.api.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        self.api.OpenProcessToken.restype = wintypes.BOOL
        self.api.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
        self.api.GetTokenInformation.restype = wintypes.BOOL
        self.api.GetLengthSid.argtypes = [ctypes.c_void_p]
        self.api.GetLengthSid.restype = wintypes.DWORD
        self.lock_name = mutex_name(target, self._user_sid())

    def _user_sid(self) -> bytes:
        token = wintypes.HANDLE()
        if not self.api.OpenProcessToken(self.kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
            raise OSError("Cannot identify Windows credential owner.")
        try:
            size = wintypes.DWORD()
            self.api.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not size.value:
                raise OSError("Cannot read Windows user identity.")
            buffer = ctypes.create_string_buffer(size.value)
            if not self.api.GetTokenInformation(token, 1, buffer, size.value, ctypes.byref(size)):
                raise OSError("Cannot read Windows user identity.")
            # TOKEN_USER begins with SID_AND_ATTRIBUTES, whose first member is PSID.
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p)).contents.value
            length = self.api.GetLengthSid(sid)
            if not length:
                raise OSError("Cannot read Windows user SID.")
            return ctypes.string_at(sid, length)
        finally:
            self.kernel.CloseHandle(token)

    @contextmanager
    def locked(self):
        """Serialize read/verify/write transactions across local processes."""
        handle = self.kernel.CreateMutexW(None, False, self.lock_name)
        if not handle:
            raise OSError("Cannot create credential lock.")
        acquired = False
        try:
            result = self.kernel.WaitForSingleObject(handle, 30000)
            acquired = result in (0, 0x80)  # acquired or abandoned by a terminated process
            if not acquired:
                raise OSError("Credential store is busy or unavailable. Retry the command.")
            yield
        finally:
            if acquired:
                self.kernel.ReleaseMutex(handle)
            self.kernel.CloseHandle(handle)

    def read(self) -> str | None:
        pointer = ctypes.POINTER(_Credential)()
        if not self.api.CredReadW(self.target, 1, 0, ctypes.byref(pointer)):
            if ctypes.get_last_error() == 1168:  # ERROR_NOT_FOUND
                return None
            raise OSError("Cannot read Windows credential.")
        try:
            value = pointer.contents
            return ctypes.string_at(value.CredentialBlob, value.CredentialBlobSize).decode("utf-8")
        finally:
            self.api.CredFree(pointer)

    def write(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 2560:
            raise OSError("Credential record exceeds Windows storage limit.")
        blob = (ctypes.c_ubyte * len(encoded)).from_buffer_copy(encoded)
        credential = _Credential()
        credential.Type = 1  # CRED_TYPE_GENERIC
        credential.TargetName = self.target
        credential.CredentialBlobSize = len(encoded)
        credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_ubyte))
        credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE; still scoped to this user
        credential.UserName = "bktstr"
        try:
            if not self.api.CredWriteW(ctypes.byref(credential), 0):
                raise OSError("Cannot save Windows credential.")
        finally:
            ctypes.memset(blob, 0, len(encoded))

    def delete(self) -> None:
        if not self.api.CredDeleteW(self.target, 1, 0) and ctypes.get_last_error() != 1168:
            raise OSError("Cannot delete Windows credential.")
