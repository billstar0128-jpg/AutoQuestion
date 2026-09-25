"""Windows 原生全局热键，无需第三方键盘钩子。"""

import ctypes
from ctypes import wintypes
import logging
from itertools import count
import sys
from typing import TYPE_CHECKING

from .config import Config, virtual_key

if TYPE_CHECKING:
    from .app import TaskRunner

LOGGER = logging.getLogger("autoquestion")
WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
_HOTKEY_IDS = count(1)


class HotkeyError(RuntimeError):
    """可安全展示的原生热键错误。"""


class WindowsHotkeys:
    """同一线程注册、监听、注销；上下文管理器确保清理。"""

    def __init__(self, config: Config) -> None:
        if sys.platform != "win32":
            raise HotkeyError("全局热键只支持 Windows 10/11。")
        self.config = config
        self.analyze_id = next(_HOTKEY_IDS)
        self.exit_id = next(_HOTKEY_IDS)
        if self.exit_id > 0xBFFF:
            raise HotkeyError("当前进程的热键 ID 已耗尽，请重新启动。")
        self._registered: list[int] = []
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self._user32.RegisterHotKey.restype = wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = wintypes.BOOL
        self._user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT
        ]
        self._user32.PeekMessageW.restype = wintypes.BOOL

    def __enter__(self) -> "WindowsHotkeys":
        try:
            for hotkey_id, key in ((self.analyze_id, self.config.hotkey), (self.exit_id, self.config.exit_key)):
                if not self._user32.RegisterHotKey(None, hotkey_id, MOD_NOREPEAT, virtual_key(key)):
                    code = ctypes.get_last_error()
                    raise HotkeyError(
                        f"无法注册 {key}（Windows 错误码 {code}）。"
                        "请关闭占用该热键的程序或修改 HOTKEY / EXIT_KEY；也请检查桌面会话权限。"
                    )
                self._registered.append(hotkey_id)
        except BaseException:
            self.close()
            raise
        return self

    def listen(self, runner: "TaskRunner") -> None:
        message = wintypes.MSG()
        while not runner.stop_event.is_set():
            if self._user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
                if message.message == 0x0012:  # WM_QUIT
                    runner.stop()
                elif message.message == WM_HOTKEY:
                    if message.wParam == self.exit_id:
                        runner.stop()
                    elif message.wParam == self.analyze_id:
                        runner.trigger()
            else:
                # 避免忙循环，也让 Ctrl+C 有机会执行。
                runner.stop_event.wait(0.02)

    def close(self) -> None:
        for hotkey_id in reversed(self._registered):
            if not self._user32.UnregisterHotKey(None, hotkey_id):
                LOGGER.error("注销热键失败（Windows 错误码 %d）。", ctypes.get_last_error())
        self._registered.clear()

    def __exit__(self, *args: object) -> None:
        self.close()
