"""One UI per Windows session/profile; activation messages contain no secrets."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys
import threading
import time

REOPEN = 0x8000 + 71
HWND_MESSAGE = -3


class DesktopInstanceError(RuntimeError):
    pass


class DesktopInstance:
    def __init__(self, profile):
        if sys.platform != 'win32':
            raise DesktopInstanceError('桌面 App 需要 Windows 10/11。')
        key = hashlib.sha256(os.path.normcase(str(Path(profile).resolve())).encode('utf-8')).hexdigest()
        self.name = 'AutoQuestion.UI.' + key
        self.primary = False
        self.handle = self.window = self.thread = self.callback = None
        self.ready = threading.Event()
        self.failed = False
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.kernel.CreateMutexW.restype = wintypes.HANDLE
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.kernel.ReleaseMutex.argtypes = self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self.kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self.user.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
        self.user.FindWindowExW.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.user.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
        self.user.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                                wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                                ctypes.POINTER(ctypes.c_size_t)]
        self.user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        self.user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user.PostMessageW.restype = wintypes.BOOL

    def __enter__(self):
        self.handle = self.kernel.CreateMutexW(None, False, 'Local\\' + self.name)
        if not self.handle:
            raise DesktopInstanceError('无法检查已有 App，请检查当前 Windows 会话。')
        result = self.kernel.WaitForSingleObject(self.handle, 0)
        if result in (0, 0x80):  # Available or abandoned by a terminated process.
            self.primary = True
        elif result != 0x102:
            self.close()
            raise DesktopInstanceError('无法检查已有 App，请重试。')
        return self

    def reopen(self, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            window = self.user.FindWindowExW(HWND_MESSAGE, None, self.name, None)
            if window:
                process = wintypes.DWORD()
                self.user.GetWindowThreadProcessId(window, ctypes.byref(process))
                self.user.AllowSetForegroundWindow(process.value)
                result = ctypes.c_size_t()
                return bool(self.user.SendMessageTimeoutW(window, REOPEN, 0, 0, 2, 2000,
                                                         ctypes.byref(result)) and result.value == 1)
            time.sleep(0.05)
        return False

    def activate(self, callback):
        if not self.primary or self.thread:
            raise DesktopInstanceError('App 实例状态无效。')
        self.callback = callback
        self.thread = threading.Thread(target=self._messages, name='autoquestion-activation', daemon=False)
        self.thread.start()
        if not self.ready.wait(5) or self.failed:
            raise DesktopInstanceError('无法创建 App 激活窗口，请重试。')

    def _messages(self):
        procedure = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                      wintypes.WPARAM, wintypes.LPARAM)
        class WindowClass(ctypes.Structure):
            _fields_ = [('style', wintypes.UINT), ('procedure', procedure),
                        ('class_extra', ctypes.c_int), ('window_extra', ctypes.c_int),
                        ('instance', wintypes.HINSTANCE), ('icon', wintypes.HICON),
                        ('cursor', wintypes.HANDLE), ('background', wintypes.HBRUSH),
                        ('menu', wintypes.LPCWSTR), ('name', wintypes.LPCWSTR)]
        user = self.user
        user.RegisterClassW.argtypes = [ctypes.POINTER(WindowClass)]
        user.RegisterClassW.restype = wintypes.WORD
        user.UnregisterClassW.argtypes = [wintypes.LPCWSTR, wintypes.HINSTANCE]
        user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
        user.CreateWindowExW.restype = wintypes.HWND
        user.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user.DefWindowProcW.restype = ctypes.c_ssize_t
        user.DestroyWindow.argtypes = [wintypes.HWND]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = ctypes.c_int
        user.TranslateMessage.argtypes = user.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        user.DispatchMessageW.restype = ctypes.c_ssize_t
        user.PostQuitMessage.argtypes = [ctypes.c_int]
        module = self.kernel.GetModuleHandleW(None)
        @procedure
        def handle(window, message, wparam, lparam):
            if message == REOPEN:
                def focus():
                    try:
                        if self.callback:
                            self.callback()
                    except Exception:
                        pass  # Closing concurrently; no raw exception or URL logs.
                threading.Thread(target=focus, daemon=True).start()
                return 1
            if message == 0x0010:
                user.DestroyWindow(window)
                return 0
            if message == 0x0002:
                user.PostQuitMessage(0)
                return 0
            return user.DefWindowProcW(window, message, wparam, lparam)
        window_class = WindowClass()
        window_class.procedure, window_class.instance, window_class.name = handle, module, self.name
        registered = False
        try:
            registered = bool(user.RegisterClassW(ctypes.byref(window_class)))
            if not registered:
                raise DesktopInstanceError('App 激活窗口注册失败。')
            self.window = user.CreateWindowExW(0, self.name, '', 0, 0, 0, 0, 0, HWND_MESSAGE, None, module, None)
            if not self.window:
                raise DesktopInstanceError('App 激活窗口创建失败。')
            self.ready.set()
            message = wintypes.MSG()
            while user.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user.TranslateMessage(ctypes.byref(message))
                user.DispatchMessageW(ctypes.byref(message))
        except Exception:
            self.failed = True
        finally:
            self.window = self.callback = None
            if registered:
                user.UnregisterClassW(self.name, module)
            self.ready.set()

    def close(self):
        if self.thread:
            self.ready.wait(5)
            if self.window:
                self.user.PostMessageW(self.window, 0x0010, 0, 0)
            self.thread.join(5)
        if self.handle:
            if self.primary:
                self.kernel.ReleaseMutex(self.handle)
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __exit__(self, *args):
        self.close()
