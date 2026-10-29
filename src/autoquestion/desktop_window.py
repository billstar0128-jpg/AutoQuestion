"""Owned Windows workbench geometry and an in-memory screen-capture exclusion."""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import os
import sys
import threading

from .capture.screen import CaptureError, own_capture_scope

COMPACT_EDGE = 80


class WindowBounds(tuple):
    """Logical bounds retain their monitor scale so saved screen positions don't drift."""
    def __new__(cls, values, scale):
        instance = super().__new__(cls, values)
        instance.scale = scale
        return instance


class DesktopWindow:
    def __init__(self, backend=None):
        self.backend = backend
        self.mode = 'normal'
        self.normal_bounds = self.compact_bounds = None
        self.lock = threading.RLock()

    def bind(self, native):
        with self.lock:
            self.backend = WinFormsWindow(native)
            self.backend.exclude_from_capture()

    def snapshot(self):
        # Never block the native event thread behind an Invoke/capture operation.
        return {'mode': self.mode, 'available': self.backend is not None}

    def set_mode(self, mode):
        if mode not in ('normal', 'compact'):
            raise ValueError('Invalid window mode')
        with self.lock:
            if self.backend is None or mode == self.mode:
                return self.snapshot()
            current = self.backend.geometry()
            if mode == 'compact':
                self.normal_bounds = current
                bounds = self.compact_bounds or WindowBounds(
                    (current[0], current[1], COMPACT_EDGE, COMPACT_EDGE), getattr(current, 'scale', 1))
            else:
                self.compact_bounds = current
                bounds = self.normal_bounds
            self.backend.apply(mode, bounds)
            self.mode = mode
            # Changing a WinForms border can recreate its HWND.
            self.backend.exclude_from_capture()
            return self.snapshot()

    @contextmanager
    def capture_scope(self):
        with own_capture_scope(self.capture_guard):
            yield

    @contextmanager
    def capture_guard(self, target):
        with self.lock:
            backend = self.backend
            if backend is None:
                yield
                return
            if target.hwnd == backend.hwnd:
                raise CaptureError('请把题目窗口放到前台，再按 F8；不能读取 AutoQuestion 自身。')
            if backend.exclude_from_capture():
                yield
                return
            shown = backend.hide_for_capture()
            try:
                yield
            finally:
                if shown:
                    backend.restore_after_capture()


class WinFormsWindow:
    """Operate on this process's WebView Form only; never activate a capture target."""
    def __init__(self, native):
        self.native = native
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.dwm = ctypes.WinDLL('dwmapi', use_last_error=True)
        for name, args, result in (
            ('GetWindowThreadProcessId', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            ('SetWindowDisplayAffinity', [wintypes.HWND, wintypes.DWORD], wintypes.BOOL),
            ('GetWindowDisplayAffinity', [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            ('GetDpiForWindow', [wintypes.HWND], wintypes.UINT),
            ('IsWindowVisible', [wintypes.HWND], wintypes.BOOL),
            ('IsIconic', [wintypes.HWND], wintypes.BOOL),
            ('ShowWindow', [wintypes.HWND, ctypes.c_int], wintypes.BOOL),
            ('SetWindowPos', [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
        ):
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.dwm.DwmFlush.argtypes, self.dwm.DwmFlush.restype = [], ctypes.c_long

    @property
    def hwnd(self):
        handle = int(self.native.Handle.ToInt64())
        pid = wintypes.DWORD()
        if not self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid)) or pid.value != os.getpid():
            raise CaptureError('无法核对本应用浮窗，已取消截图。')
        return handle

    def _invoke(self, action):
        if not self.native.InvokeRequired:
            return action()
        from System import Action
        result, errors = [], []
        def run():
            try:
                result.append(action())
            except Exception as error:
                errors.append(error)
        self.native.Invoke(Action(run))
        if errors:
            raise errors[0]
        return result[0] if result else None

    def geometry(self):
        def read():
            scale = self.user.GetDpiForWindow(self.hwnd) / 96.0
            if scale <= 0:
                raise CaptureError('无法读取浮窗显示比例。')
            bounds = self.native.Bounds
            return WindowBounds(tuple(round(value / scale) for value in
                                      (bounds.X, bounds.Y, bounds.Width, bounds.Height)), scale)
        return self._invoke(read)

    def apply(self, mode, bounds):
        def change():
            from System.Drawing import Size, Rectangle
            from System.Windows.Forms import FormBorderStyle, FormWindowState
            compact = mode == 'compact'
            self.native.WindowState = FormWindowState.Normal
            scale = getattr(bounds, 'scale', self.user.GetDpiForWindow(self.hwnd) / 96.0)
            if scale <= 0:
                raise CaptureError('无法读取浮窗显示比例。')
            self.native.MinimumSize = Size(0, 0)
            self.native.FormBorderStyle = getattr(FormBorderStyle, 'None') if compact else FormBorderStyle.Sizable
            self.native.MaximizeBox = not compact
            self.native.TopMost = compact
            self.native.Bounds = Rectangle(*(round(value * scale) for value in bounds))
            if not compact:
                current_scale = self.user.GetDpiForWindow(self.hwnd) / 96.0
                self.native.MinimumSize = Size(round(320 * current_scale), round(360 * current_scale))
            # pywebview reads these flags when exposing current native state.
            self.native.pywebview_window.frameless = compact
            self.native.pywebview_window.resizable = not compact
        self._invoke(change)

    def exclude_from_capture(self):
        if sys.getwindowsversion().build < 19041:
            return False  # Older systems turn 0x11 into a black rectangle.
        hwnd = self.hwnd
        value = wintypes.DWORD()
        return bool(self.user.SetWindowDisplayAffinity(hwnd, 0x11)
                    and self.user.GetWindowDisplayAffinity(hwnd, ctypes.byref(value)) and value.value == 0x11)

    def hide_for_capture(self):
        hwnd = self.hwnd
        visible = bool(self.user.IsWindowVisible(hwnd)) and not self.user.IsIconic(hwnd)
        if visible:
            # Hide only the owned HWND, retaining the question's focus and z-order.
            if not self.user.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x80 | 0x10 | 0x01 | 0x02 | 0x04):
                raise CaptureError('无法暂时隐藏本应用浮窗，已取消截图。')
            if self.dwm.DwmFlush() < 0:
                self.restore_after_capture()
                raise CaptureError('无法同步浮窗画面，已取消截图。')
        return visible

    def restore_after_capture(self):
        self.user.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE: never steal the F8 target.
