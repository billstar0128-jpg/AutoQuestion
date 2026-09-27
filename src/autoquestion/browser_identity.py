"""Windows executable identity and loopback TCP ownership; never inspect page titles."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
import ntpath
import socket
import sys


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    image: str = field(repr=False)
    born: int


class BrowserClassifier:
    @staticmethod
    def classify(image):
        return {'chrome.exe': 'Chrome', 'msedge.exe': 'Edge'}.get(ntpath.basename(image).lower())


def process_identity(pid):
    """Limited query rights, no process memory, command line, profile or environment."""
    if sys.platform != 'win32':
        raise OSError('Windows process identity unavailable.')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                 ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise OSError('Process identity unavailable.')
    try:
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        times = [wintypes.FILETIME() for _ in range(4)]
        if (not kernel.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size))
                or not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times))):
            raise OSError('Process identity unavailable.')
        born = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return ProcessIdentity(pid, ntpath.normcase(image.value), born)
    finally:
        kernel.CloseHandle(handle)


def _parents():
    class Entry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD), ('pid', wintypes.DWORD),
                    ('heap', ctypes.c_size_t), ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', ctypes.c_long), ('flags', wintypes.DWORD),
                    ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    for name in ('Process32FirstW', 'Process32NextW'):
        getattr(kernel, name).argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError('Process ancestry unavailable.')
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        result = {}
        while found:
            result[entry.pid] = entry.parent
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
        return result
    finally:
        kernel.CloseHandle(handle)


def tcp_owner(client_port, server_port):
    """Resolve exact IPv4 loopback client tuple, not arbitrary browser processes."""
    class Row(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in ('state', 'local', 'lport', 'remote', 'rport', 'pid')]
    function = ctypes.WinDLL('iphlpapi').GetExtendedTcpTable
    function.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL,
                         wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    function.restype = wintypes.DWORD
    size = wintypes.DWORD()
    function(None, ctypes.byref(size), False, socket.AF_INET, 5, 0)
    for _ in range(3):
        buffer = ctypes.create_string_buffer(size.value)
        code = function(buffer, ctypes.byref(size), False, socket.AF_INET, 5, 0)
        if code == 122:
            continue
        if code:
            break
        count = wintypes.DWORD.from_buffer(buffer).value
        loopback = int.from_bytes(socket.inet_aton('127.0.0.1'), 'little')
        matches = []
        for i in range(count):
            row = Row.from_buffer(buffer, 4 + i * ctypes.sizeof(Row))
            if (row.state == 5 and row.local == row.remote == loopback
                    and socket.ntohs(row.lport & 65535) == client_port
                    and socket.ntohs(row.rport & 65535) == server_port):
                matches.append(row.pid)
        if len(matches) == 1:
            return matches[0]
        break
    raise OSError('Loopback client ownership unavailable.')


def browser_peer(client_port, server_port):
    """Network-service children must belong to the same executable and live parent chain."""
    identity = process_identity(tcp_owner(client_port, server_port))
    if not BrowserClassifier.classify(identity.image):
        raise OSError('Client is not a supported browser.')
    parents = _parents()
    seen = set()
    for _ in range(16):
        if identity.pid in seen:
            raise OSError('Process ancestry ambiguous.')
        seen.add(identity.pid)
        parent_pid = parents.get(identity.pid, 0)
        if not parent_pid:
            break
        try:
            parent = process_identity(parent_pid)
        except OSError:
            break
        if parent.image != identity.image or parent.born >= identity.born:
            break
        identity = parent
    return identity
