"""Small Windows Credential Manager adapter; no plaintext fallback.

Metadata operations never dereference CredentialBlob. Only get() decodes a
secret, exclusively for normal runtime use. Tests inject a fake backend/API.
"""
import ctypes
from ctypes import wintypes
import re
import sys
from typing import Protocol
from uuid import uuid4

from pydantic import SecretStr


class CredentialError(RuntimeError):
    pass


def valid_identifier(identifier):
    return isinstance(identifier, str) and re.fullmatch(r'AutoQuestion/[a-z][a-z0-9_]{0,63}/[a-f0-9]{32}', identifier) is not None


def new_identifier(profile):
    identifier = f'AutoQuestion/{profile}/{uuid4().hex}'
    if not valid_identifier(identifier):
        raise CredentialError('Credential identifier 无效。')
    return identifier


class CredentialBackend(Protocol):
    def list_ids(self) -> tuple[str, ...]: ...
    def exists(self, identifier: str) -> bool: ...
    def get(self, identifier: str) -> SecretStr | None: ...
    def put(self, identifier: str, secret: SecretStr) -> None: ...
    def delete(self, identifier: str) -> None: ...


class Credential(ctypes.Structure):
    _fields_ = [('Flags', wintypes.DWORD), ('Type', wintypes.DWORD),
                ('TargetName', wintypes.LPWSTR), ('Comment', wintypes.LPWSTR),
                ('LastWritten', wintypes.FILETIME), ('CredentialBlobSize', wintypes.DWORD),
                ('CredentialBlob', ctypes.POINTER(ctypes.c_ubyte)), ('Persist', wintypes.DWORD),
                ('AttributeCount', wintypes.DWORD), ('Attributes', ctypes.c_void_p),
                ('TargetAlias', wintypes.LPWSTR), ('UserName', wintypes.LPWSTR)]


Pointer = ctypes.POINTER(Credential)


class WindowsCredentials:
    def __init__(self, api=None):
        self._api = api

    def _native(self):
        if self._api is None:
            if sys.platform != 'win32':
                raise CredentialError('Secure credential storage is unavailable.')
            api = ctypes.WinDLL('advapi32', use_last_error=True)
            signatures = {
                'CredReadW': [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Pointer)],
                'CredWriteW': [Pointer, wintypes.DWORD],
                'CredDeleteW': [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD],
                'CredEnumerateW': [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ctypes.POINTER(Pointer))],
            }
            for name, arguments in signatures.items():
                function = getattr(api, name)
                function.argtypes, function.restype = arguments, wintypes.BOOL
            api.CredFree.argtypes, api.CredFree.restype = [ctypes.c_void_p], None
            self._api = api
        return self._api

    def list_ids(self):
        try:
            api = self._native()
            count, entries = wintypes.DWORD(), ctypes.POINTER(Pointer)()
            if not api.CredEnumerateW('AutoQuestion/*', 0, ctypes.byref(count), ctypes.byref(entries)):
                if ctypes.get_last_error() == 1168:
                    return ()
                raise CredentialError()
            try:
                # Only names/types: never read, stringify or hash blob contents.
                return tuple(entries[i].contents.TargetName for i in range(count.value)
                             if entries[i].contents.Type == 1 and valid_identifier(entries[i].contents.TargetName))
            finally:
                api.CredFree(entries)
        except Exception:
            raise CredentialError('Secure credential storage is unavailable.') from None

    def exists(self, identifier):
        return valid_identifier(identifier) and identifier in self.list_ids()

    def get(self, identifier):
        try:
            if not valid_identifier(identifier):
                raise CredentialError()
            api, entry = self._native(), Pointer()
            if not api.CredReadW(identifier, 1, 0, ctypes.byref(entry)):
                if ctypes.get_last_error() == 1168:
                    return None
                raise CredentialError()
            try:
                size = entry.contents.CredentialBlobSize
                if not 0 < size <= 2560:
                    raise CredentialError()
                return SecretStr(ctypes.string_at(entry.contents.CredentialBlob, size).decode('utf-8'))
            finally:
                api.CredFree(entry)
        except Exception:
            raise CredentialError('无法读取安全凭据；可以使用 session-only 模式。') from None

    def put(self, identifier, secret):
        buffer = None
        try:
            if not valid_identifier(identifier) or not isinstance(secret, SecretStr):
                raise CredentialError()
            encoded = secret.get_secret_value().encode('utf-8')
            if not 0 < len(encoded) <= 2560:
                raise CredentialError()
            buffer = ctypes.create_string_buffer(encoded)
            entry = Credential(Type=1, TargetName=identifier, UserName='AutoQuestion', Persist=2,
                               CredentialBlobSize=len(encoded),
                               CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
            if not self._native().CredWriteW(ctypes.byref(entry), 0):
                raise CredentialError()
        except Exception:
            raise CredentialError('Secure credential storage is unavailable; Key 未写入普通配置。') from None
        finally:
            if buffer is not None:
                ctypes.memset(buffer, 0, ctypes.sizeof(buffer))

    def delete(self, identifier):
        try:
            if not valid_identifier(identifier):
                raise CredentialError()
            if not self._native().CredDeleteW(identifier, 1, 0) and ctypes.get_last_error() != 1168:
                raise CredentialError()
        except Exception:
            raise CredentialError('无法删除所选 AutoQuestion 凭据；未输出凭据内容。') from None
