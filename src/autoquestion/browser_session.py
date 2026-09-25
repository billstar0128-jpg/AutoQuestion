"""本轮只管理内置本地 Demo；专用线程持有全部 Playwright 对象。"""

from collections.abc import Awaitable, Callable
from concurrent.futures import TimeoutError
import asyncio
import inspect
import threading
import logging
import os
from pathlib import Path
from typing import TypeVar

from playwright.async_api import Browser, Error as PlaywrightError, Playwright, async_playwright

from .capture.browser import AsyncBrowserDOMAdapter, BrowserExtractionError
from .capture.screen import WindowTarget, WindowsWindowAPI
from .schemas import Question

LOGGER = logging.getLogger("autoquestion")
DEMO_PATH = Path(__file__).resolve().parents[2] / "examples" / "demo_quiz.html"
CANVAS_PATH = DEMO_PATH.with_name("demo_canvas_quiz.html")
DEMO_URLS = {DEMO_PATH.as_uri(), CANVAS_PATH.as_uri()}
T = TypeVar("T")


class BrowserSession:
    """专用 asyncio 线程持续分发导航事件；对外仍提供同步接口，不替换任务锁。"""

    def __init__(self, *, headless: bool = False) -> None:
        self._headless = headless
        self._loop = asyncio.new_event_loop()
        self._operation_lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._adapter: AsyncBrowserDOMAdapter | None = None
        self._closed = False
        self._failed = False
        self._process_id = 0
        self._thread = threading.Thread(target=self._run_loop, name="autoquestion-browser", daemon=False)
        self._thread.start()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.run_until_complete(self._loop.shutdown_default_executor())
            self._loop.close()

    async def _run_operation(self, operation: Callable[[], T | Awaitable[T]]) -> T:
        # 操作仍串行；await 时 route/load 等事件继续运行，READY 时也持续分发。
        async with self._operation_lock:
            result = operation()
            return await result if inspect.isawaitable(result) else result

    def _call(self, operation: Callable[[], T | Awaitable[T]]) -> T:
        if self._closed or self._failed:
            raise BrowserExtractionError("浏览器会话已关闭或不可用，请重启 DOM 模式。")
        try:
            return asyncio.run_coroutine_threadsafe(self._run_operation(operation), self._loop).result(timeout=25)
        except TimeoutError:
            self._failed = True
            raise BrowserExtractionError("浏览器操作超时，请关闭并重启 DOM 模式。") from None

    def start(self) -> None:
        self._call(self._open)

    async def _open(self) -> None:
        if self._adapter is not None:
            return
        if not DEMO_PATH.is_file():
            raise BrowserExtractionError("找不到 examples/demo_quiz.html。")
        # 默认浏览器 runtime 放在虚拟环境的 Playwright 包内，不依赖个人浏览器。
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")
        try:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=self._headless, timeout=15000)
            context = await self._browser.new_context(accept_downloads=False, service_workers="block")
            demo_url = DEMO_PATH.as_uri()
            async def route_request(route):
                if route.request.url in DEMO_URLS:
                    await route.continue_()
                else:
                    await route.abort()
            await context.route("**/*", route_request)
            page = await context.new_page()
            await page.goto(demo_url, wait_until="load", timeout=5000)
            self._adapter = AsyncBrowserDOMAdapter(page)
            # 仅查询本次启动的 Chromium；失败不会破坏强制 DOM 模式。
            session = None
            try:
                session = await self._browser.new_browser_cdp_session()
                processes = (await session.send("SystemInfo.getProcessInfo"))["processInfo"]
                self._process_id = next(int(item["id"]) for item in processes if item["type"] == "browser")
            except (PlaywrightError, KeyError, StopIteration, ValueError):
                self._process_id = 0
            finally:
                if session is not None:
                    try:
                        await session.detach()
                    except PlaywrightError:
                        self._process_id = 0
        except PlaywrightError:
            raise BrowserExtractionError(
                "无法启动本地 Chromium；请在 .venv-win 中安装 Playwright Chromium runtime。"
            ) from None

    def extract_question(self) -> Question:
        async def extract() -> Question:
            if self._adapter is None:
                raise BrowserExtractionError("浏览器会话尚未启动。")
            if self._adapter.page.is_closed() or self._adapter.page.url not in DEMO_URLS:
                raise BrowserExtractionError("受管理页面已关闭或离开本地 Demo，请重启 DOM 模式。")
            return await self._adapter.extract_question()
        return self._call(extract)

    def extract_for_target(self, target: WindowTarget, verify: Callable[[], None]) -> Question:
        """AUTO 专用：PID、唯一窗口/页面及焦点一致才读 DOM。"""
        if not self._process_id or target.process_id != self._process_id:
            raise BrowserExtractionError("当前窗口不是受管理浏览器。")
        async def extract() -> Question:
            try:
                verify()
                if self._browser is None or not self._browser.is_connected() or self._adapter is None:
                    raise BrowserExtractionError("受管理浏览器不可用。")
                page = self._adapter.page
                pages = [p for context in self._browser.contexts for p in context.pages]
                if (pages != [page] or page.is_closed() or page.url not in DEMO_URLS
                        or WindowsWindowAPI().browser_windows(self._process_id) != [target.hwnd]
                        or not await page.evaluate("document.hasFocus() && document.visibilityState === 'visible'")):
                    raise BrowserExtractionError("无法唯一对应前台浏览器页面。")
                question = await self._adapter.extract_question()
                verify()
                if not await page.evaluate("document.hasFocus() && document.visibilityState === 'visible'"):
                    raise BrowserExtractionError("页面焦点已变化。")
                return question
            except PlaywrightError:
                raise BrowserExtractionError("受管理页面连接或获取失败。") from None
        return self._call(extract)

    def close(self) -> None:
        """等待任务结束后在所属线程关闭浏览器与 driver，不留下浏览器线程。"""
        if self._closed:
            return
        self._closed = True
        async def cleanup() -> None:
            try:
                if self._browser is not None:
                    await self._browser.close()
            except PlaywrightError:
                LOGGER.warning("浏览器已断开，正在释放本地驱动。")
            finally:
                if self._playwright is not None:
                    await self._playwright.stop()
        try:
            asyncio.run_coroutine_threadsafe(self._run_operation(cleanup), self._loop).result()
        except PlaywrightError:
            LOGGER.warning("浏览器驱动清理失败，请检查是否仍有本次启动的 Chromium 进程。")
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join()
