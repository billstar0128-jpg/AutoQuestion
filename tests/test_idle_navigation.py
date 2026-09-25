"""模拟用户在 READY 空闲期间点击链接，不用 goto/wait 调用替浏览器泵事件。"""
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.browser_session import BrowserSession, CANVAS_PATH, DEMO_PATH
from autoquestion.capture.browser import BrowserExtractionError


class NavigationProbe:
    """仅测试：通过新文档 load 回报 readyState、实际绘制文字和像素。"""
    def __init__(self, browser):
        self.browser = browser
        self.loaded = threading.Event()
        self.payload = None
        self.errors = []
        def receive(payload):
            self.payload = payload
            self.loaded.set()
        browser._call(lambda: browser._adapter.page.context.expose_function('__test_loaded', receive))
        browser._call(lambda: browser._adapter.page.on('pageerror', lambda error: self.errors.append(str(error))))
        browser._call(lambda: browser._adapter.page.context.add_init_script('''
            const drawn = [];
            const fill = CanvasRenderingContext2D.prototype.fillText;
            CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
                drawn.push(text); return fill.call(this, text, ...args);
            };
            addEventListener('load', () => {
                const canvas = document.querySelector('canvas');
                const bands = canvas ? [64,128,192,256,320].map(y => {
                    const pixels = canvas.getContext('2d').getImageData(0, (y-30)*2, 1440, 64).data;
                    return pixels.some((value, i) => i % 4 === 3 && value > 0);
                }) : [];
                window.__test_loaded({url: location.href, ready: document.readyState,
                    drawn, bands, canvas: Boolean(canvas)});
            });
        '''))

    def click_while_idle(self, text, timeout=5):
        self.loaded.clear()
        self.payload = None
        # 浏览器自己的定时器模拟用户稍后点击；返回后禁止调用 BrowserSession，
        # 让测试等待期间的导航完全依赖会话自身的事件循环。
        self.browser._call(lambda: self.browser._adapter.page.evaluate('''text => {
            const link = [...document.querySelectorAll('a')].find(a => a.textContent === text);
            if (!link) throw new Error('Test link missing');
            setTimeout(() => link.click(), 100);
        }''', text))
        return self.loaded.wait(timeout)


class IdleNavigationTests(unittest.TestCase):
    def test_disallowed_request_is_aborted_even_while_idle(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        browser.start()
        failed = threading.Event()
        failures = []
        def on_failed(request):
            failures.append((request.url, request.failure))
            failed.set()
        browser._call(lambda: browser._adapter.page.on('requestfailed', on_failed))
        browser._call(lambda: browser._adapter.page.evaluate('''() => {
            setTimeout(() => fetch('https://example.invalid/blocked').catch(() => {}), 100);
        }'''))
        self.assertTrue(failed.wait(5))
        self.assertEqual(failures, [('https://example.invalid/blocked', 'net::ERR_FAILED')])
        self.assertEqual(browser.extract_question().question_text, '法国的首都是哪里？')

    def test_canvas_and_return_load_while_no_f8_or_playwright_calls(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        browser.start()
        self.assertEqual(browser.extract_question().question_text, '法国的首都是哪里？')
        probe = NavigationProbe(browser)
        completed_while_idle = probe.click_while_idle('打开 Canvas 测试题')
        if not completed_while_idle:
            # 复现诊断：恢复一次 Playwright 调用便能完成同一导航和绘图。
            browser._call(lambda: browser._adapter.page.wait_for_url(CANVAS_PATH.as_uri(), wait_until='load'))
            print('Idle navigation stalled; pumping Playwright completed load:', probe.loaded.wait(1))
        self.assertTrue(completed_while_idle, '空闲期间导航被挂起，必须等下一次 Playwright 调用才加载')
        self.assertEqual(probe.payload['url'], CANVAS_PATH.as_uri())
        self.assertEqual(probe.payload['ready'], 'complete')
        self.assertEqual(probe.payload['drawn'], ['太阳系中最大的行星是？', '木星', '地球', '火星', '金星'])
        self.assertEqual(probe.payload['bands'], [True] * 5)
        self.assertFalse(probe.errors)
        with self.assertRaises(BrowserExtractionError):
            browser.extract_question()
        self.assertTrue(probe.click_while_idle('返回 DOM 测试题'))
        self.assertEqual(probe.payload['url'], DEMO_PATH.as_uri())
        self.assertEqual(probe.payload['ready'], 'complete')
        self.assertEqual(browser.extract_question().question_text, '法国的首都是哪里？')
