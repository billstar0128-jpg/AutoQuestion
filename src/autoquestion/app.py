"""任务生命周期独立于 Windows，方便测试和以后替换识题回调。"""

from collections.abc import Callable
from enum import Enum
import logging
import threading
import time

from .config import ConfigError, load_config, load_env_file
from .capture.screen import CaptureError
from .capture.browser import BrowserExtractionError
from .llm.base import LLMProviderError
from .schemas import AnswerValidationError

LOGGER = logging.getLogger("autoquestion")


class Status(str, Enum):
    READY = "READY"
    WORKING = "WORKING"
    CAPTURING = "CAPTURING"
    ANALYZING = "ANALYZING"
    EXTRACTING = "EXTRACTING"
    ROUTING = "ROUTING"
    BUSY = "BUSY"
    ERROR = "ERROR"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


def demo_callback(stop: threading.Event) -> None:
    """短暂模拟耗时工作；ESC 能打断等待。"""
    stop.wait(0.15)


class TaskRunner:
    """锁保护防抖和 busy 状态；不排队，最多一个任务。"""

    def __init__(
        self,
        callback: Callable[[threading.Event], None] = demo_callback,
        debounce_ms: int = 400,
        clock: Callable[[], float] = time.monotonic,
        prepare: Callable[[], Callable[[threading.Event], None]] | None = None,
        prepare_status: Status = Status.CAPTURING,
    ) -> None:
        self._callback = callback
        self._prepare = prepare
        self._prepare_status = prepare_status
        self._debounce = debounce_ms / 1000
        self._clock = clock
        self._lock = threading.Lock()
        self._last_trigger = float("-inf")
        self._busy = False
        self._worker: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.trigger_count = 0
        self.state = Status.READY

    def _set_status(self, status: Status) -> None:
        self.state = status
        LOGGER.info("Status: %s", status.value)

    def ready(self) -> None:
        self._set_status(Status.READY)

    def update_status(self, status: str) -> None:
        """供工作流程更新状态；退出后不再打印分析状态。"""
        with self._lock:
            if not self.stop_event.is_set():
                self._set_status(Status(status))

    def trigger(self) -> bool:
        """返回是否接受任务；重复事件不会创建额外工作线程。"""
        with self._lock:
            if self.stop_event.is_set():
                return False
            if self._busy:
                self._set_status(Status.BUSY)
                return False
            now = self._clock()
            if now - self._last_trigger < self._debounce:
                LOGGER.info("Ignored: debounce")
                return False
            self._last_trigger = now
            self._busy = True
            # 先记录目标 HWND/bounds，再输出任何日志；busy/debounce 已在之前检查。
            try:
                callback = self._prepare() if self._prepare is not None else self._callback
            except Exception as exc:
                self._busy = False
                self._set_status(Status.ERROR)
                if isinstance(exc, (CaptureError, ConfigError, LLMProviderError)):
                    LOGGER.error("ERROR: %s", exc)
                else:
                    LOGGER.error("准备当前任务失败，请重新按 F8。")
                self._set_status(Status.READY)
                return False
            self.trigger_count += 1
            LOGGER.info("Triggered #%d", self.trigger_count)
            self._set_status(self._prepare_status if self._prepare is not None else Status.WORKING)
            self._worker = threading.Thread(
                target=self._run_callback, args=(callback,), name="autoquestion-worker", daemon=False
            )
            try:
                self._worker.start()
            except RuntimeError:
                self._worker = None
                self._busy = False
                self._set_status(Status.ERROR)
                LOGGER.error("无法启动工作线程，请检查系统资源。")
                self._set_status(Status.READY)
                return False
            return True

    def _run_callback(self, callback: Callable[[threading.Event], None]) -> None:
        try:
            callback(self.stop_event)
        except (BrowserExtractionError, CaptureError, ConfigError, LLMProviderError, AnswerValidationError) as exc:
            with self._lock:
                if not self.stop_event.is_set():
                    self._set_status(Status.ERROR)
                LOGGER.error("ERROR: %s", exc)
        except Exception:
            # 原始第三方异常可能含请求头、密钥或响应体，不直接输出。
            with self._lock:
                if not self.stop_event.is_set():
                    self._set_status(Status.ERROR)
                LOGGER.error("测试回调执行失败；已恢复，可再次按热键。")
        finally:
            with self._lock:
                self._busy = False
                if not self.stop_event.is_set():
                    self._set_status(Status.READY)

    def stop(self) -> None:
        """协作退出；不强行杀线程。未来网络回调必须设置超时。"""
        with self._lock:
            if not self.stop_event.is_set():
                self.stop_event.set()
                self._set_status(Status.STOPPING)

    def close(self) -> None:
        self.stop()
        # join 放在锁外，避免与回调的 finally 死锁。
        if self._worker is not None:
            self._worker.join()
        self._set_status(Status.STOPPED)


def main(argv: list[str] | None = None, *, parsed_args=None, runtime=None) -> int:
    from .cli import parse_args
    args = parsed_args if parsed_args is not None else parse_args(argv)
    if args.doctor:
        from .doctor import run_doctor
        return run_doctor(env_file_requested=args.env_file is not None)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    from .hotkeys import HotkeyError, WindowsHotkeys

    runner: TaskRunner | None = None
    browser = None
    try:
        if runtime is None and args.env_file is not None:
            load_env_file(args.env_file)
        config = runtime.config if runtime is not None else load_config()
        open_demo = args.open_demo or (runtime is not None and runtime.open_demo)
        if open_demo and config.input_mode == "demo":
            raise ConfigError("--open-demo 不能与 INPUT_MODE=demo 组合；固定 MANUAL Demo 不使用浏览器。")
        # Only allocate the session (and its event-loop thread) when requested.
        if config.input_mode == "dom" or open_demo:
            from .browser_session import BrowserSession
            browser = BrowserSession()
            try:
                browser.start()
            except BrowserExtractionError:
                if config.input_mode == "dom":
                    raise
                browser.close()
                browser = None
                LOGGER.warning("受管理 Demo 启动失败；仍可使用 Vision。请检查 Chromium runtime。")
        from .demo import make_demo_callback
        if config.input_mode == "vision":
            from .vision import make_vision_prepare
            prepare = make_vision_prepare(config, lambda status: runner.update_status(status))
            runner = TaskRunner(prepare=prepare, debounce_ms=config.debounce_ms)
        elif config.input_mode in {"dom", "auto"}:
            from .dom import make_dom_callback
            if config.input_mode == "auto":
                from .router import make_auto_prepare
                runner = TaskRunner(prepare=make_auto_prepare(config, browser, lambda status: runner.update_status(status)),
                                    debounce_ms=config.debounce_ms, prepare_status=Status.ROUTING)
            else:
                runner = TaskRunner(callback=make_dom_callback(config, browser, lambda status: runner.update_status(status)),
                                    debounce_ms=config.debounce_ms)
        else:
            runner = TaskRunner(callback=make_demo_callback(config), debounce_ms=config.debounce_ms)
        with WindowsHotkeys(config) as hotkeys:
            from . import __version__
            LOGGER.info(
                "AutoQuestion %s\n====================\n[%s] Analyze current question\n[%s] Exit",
                __version__, config.hotkey, config.exit_key,
            )
            LOGGER.info("Provider: %s", "FAKE (offline demo)" if config.llm_provider == "fake"
                        else "OPENAI (configured API)")
            LOGGER.info("Input mode: %s", config.input_mode)
            if config.input_mode == "vision":
                if browser is not None:
                    LOGGER.info("Demo opened for visual testing; Vision mode will not use DOM.")
                LOGGER.info("Vision: F8 将把前台窗口截图发送给你配置的模型服务商；截图不保存到磁盘。")
            elif config.input_mode == "dom":
                LOGGER.info("DOM: 分析受管理 Chromium 中的当前 Demo 题目；请手动点击上一题/下一题。")
            elif config.input_mode == "auto":
                if browser is None:
                    LOGGER.info("Managed Demo: not open. AUTO uses Vision for the foreground target; --open-demo enables local DOM testing.")
                LOGGER.info("AUTO: 前台受管理页面优先 DOM；取题不可用时截取 F8 目标窗口并发送给配置的 Vision 服务商。截图不保存。")
            runner.ready()
            hotkeys.listen(runner)
        return 0
    except (BrowserExtractionError, ConfigError, HotkeyError) as exc:
        LOGGER.error("启动失败：%s", exc)
        return 1
    except KeyboardInterrupt:
        LOGGER.info("收到 Ctrl+C，正在退出。")
        return 0
    except Exception:
        LOGGER.error("程序发生未预期错误，正在清理；未输出可能包含敏感信息的异常内容。")
        return 1
    finally:
        try:
            if runner is not None:
                runner.close()
        finally:
            if browser is not None:
                browser.close()
