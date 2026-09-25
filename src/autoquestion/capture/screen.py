"""前台窗口的可见屏幕区域截图；所有像素仅在内存中流转。"""

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import dataclass, field
from io import BytesIO
import logging
import sys
from typing import Iterator

import mss
from PIL import Image

LOGGER = logging.getLogger("autoquestion")
MAX_CAPTURE_PIXELS = 32_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_EDGE = 2048


class CaptureError(RuntimeError):
    """可安全显示的截图错误，不包含窗口标题或像素。"""


@dataclass(frozen=True)
class WindowTarget:
    hwnd: int
    process_id: int
    left: int
    top: int
    right: int
    bottom: int
    title: str = field(default="", repr=False, compare=False)

    @property
    def region(self) -> dict[str, int]:
        return dict(left=self.left, top=self.top,
                    width=self.right - self.left, height=self.bottom - self.top)


@dataclass(frozen=True)
class CapturedImage:
    """Provider 只需要图片数据，不需要 HWND 或 Windows 依赖。"""

    data: bytes = field(repr=False)
    width: int
    height: int
    media_type: str = "image/png"

    def __post_init__(self) -> None:
        if (not isinstance(self.data, bytes) or not self.data.startswith(b"\x89PNG\r\n\x1a\n")
                or len(self.data) > MAX_IMAGE_BYTES or self.media_type != "image/png"
                or self.width <= 0 or self.height <= 0 or max(self.width, self.height) > 4096):
            raise CaptureError("截图格式、尺寸或编码大小无效。")


class WindowsWindowAPI:
    """轻量 ctypes 封装；每个调用线程临时使用 Per Monitor V2 DPI。"""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise CaptureError("前台窗口捕获仅支持 Windows 10/11。")
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        signatures = {
            "GetForegroundWindow": ([], wintypes.HWND),
            "GetWindowTextW": ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            "GetClassNameW": ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            "IsWindow": ([wintypes.HWND], wintypes.BOOL),
            "IsWindowVisible": ([wintypes.HWND], wintypes.BOOL),
            "IsIconic": ([wintypes.HWND], wintypes.BOOL),
            "GetWindowRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            "SetThreadDpiAwarenessContext": ([ctypes.c_void_p], ctypes.c_void_p),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user32, name)
            function.argtypes, function.restype = args, result
        self.dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                     ctypes.c_void_p, wintypes.DWORD]
        self.dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    @contextmanager
    def physical_coordinates(self) -> Iterator[None]:
        previous = self.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        if not previous:
            raise CaptureError("无法启用当前线程的 DPI 感知，已取消截图。")
        try:
            yield
        finally:
            if not self.user32.SetThreadDpiAwarenessContext(previous):
                raise CaptureError("无法恢复线程 DPI 上下文。")

    def foreground(self) -> int:
        return self.user32.GetForegroundWindow() or 0

    def describe(self, hwnd: int) -> WindowTarget:
        if (not hwnd or not self.user32.IsWindow(hwnd)
                or not self.user32.IsWindowVisible(hwnd) or self.user32.IsIconic(hwnd)):
            raise CaptureError("Unable to capture foreground window. 窗口不存在、不可见或已最小化。")
        process_id = wintypes.DWORD()
        if not self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id)):
            raise CaptureError("无法读取前台窗口标识。")
        rect = wintypes.RECT()
        # DWM 可见边界不含不可见缩放边框，坐标是物理像素。
        result = self.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
        if result != 0 and not self.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise CaptureError("无法读取前台窗口边界。")
        if rect.right <= rect.left or rect.bottom <= rect.top:
            raise CaptureError("前台窗口没有有效截图区域。")
        title = ctypes.create_unicode_buffer(4096)
        self.user32.GetWindowTextW(hwnd, title, len(title))
        return WindowTarget(hwnd, process_id.value, rect.left, rect.top, rect.right, rect.bottom, title.value)

    def browser_windows(self, process_id: int) -> list[int]:
        """只返回指定自有进程的可见 Chromium 顶层窗口，不读取其他窗口标题。"""
        handles = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, parameter):
            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == process_id and self.user32.IsWindowVisible(hwnd):
                name = ctypes.create_unicode_buffer(256)
                self.user32.GetClassNameW(hwnd, name, len(name))
                if name.value == "Chrome_WidgetWin_1":
                    handles.append(hwnd)
            return True
        self.user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user32.EnumWindows.restype = wintypes.BOOL
        if not self.user32.EnumWindows(callback_type(visit), 0):
            raise CaptureError("无法核对受管理浏览器窗口。")
        return handles


class ScreenCapture:
    def __init__(self, max_edge: int = DEFAULT_MAX_EDGE) -> None:
        if not 1024 <= max_edge <= 4096:
            raise CaptureError("截图最长边必须为 1024～4096 像素。")
        self.max_edge = max_edge
        self._windows = WindowsWindowAPI()

    def snapshot_target(self) -> WindowTarget:
        """由热键任务准备步骤调用，先记录目标，再允许任何状态日志。"""
        try:
            with self._windows.physical_coordinates():
                hwnd = self._windows.foreground()
                target = self._windows.describe(hwnd)
                if self._windows.foreground() != hwnd:
                    raise CaptureError("前台窗口已切换，请保持题目窗口在前台后重试。")
                return target
        except CaptureError:
            raise
        except Exception:
            raise CaptureError("Unable to capture foreground window. 无法读取窗口信息。") from None

    def _verify_target(self, target: WindowTarget) -> None:
        if self._windows.foreground() != target.hwnd or self._windows.describe(target.hwnd) != target:
            raise CaptureError("目标窗口已切换、移动或关闭，已取消本次截图，请重新按 F8。")

    def verify_target(self, target: WindowTarget) -> None:
        """仅核对 F8 目标，不产生任何像素。"""
        with self._windows.physical_coordinates():
            self._verify_target(target)

    def capture(self, target: WindowTarget) -> CapturedImage:
        """只截预先记录的窗口矩形；目标变化时拒绝，不退回全屏。"""
        try:
            with self._windows.physical_coordinates():
                self._verify_target(target)
                region = target.region
                if region["width"] * region["height"] > MAX_CAPTURE_PIXELS:
                    raise CaptureError("窗口原始像素过大，请缩小窗口后重试。")
                with mss.MSS() as grabber:
                    desktop = grabber.monitors[0]
                    if (target.left < desktop["left"] or target.top < desktop["top"]
                            or target.right > desktop["left"] + desktop["width"]
                            or target.bottom > desktop["top"] + desktop["height"]):
                        raise CaptureError("窗口部分位于屏幕之外，请将整道题移入可见区域。")
                    shot = grabber.grab(region)
                    self._verify_target(target)
                    with Image.frombytes("RGB", shot.size, shot.rgb) as image:
                        image.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                        with BytesIO() as buffer:
                            image.save(buffer, format="PNG")
                            result = CapturedImage(buffer.getvalue(), image.width, image.height)
                LOGGER.debug("Capture dimensions: %dx%d; encoded dimensions: %dx%d",
                             region["width"], region["height"], result.width, result.height)
                return result
        except CaptureError:
            raise
        except Exception:
            raise CaptureError("Screenshot failure. 截图或图像编码失败，请重试。") from None
