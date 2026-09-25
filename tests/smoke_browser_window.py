"""显式运行的可见 Windows 冒烟测试；只使用自建窗口、合成图片和 Fake。"""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.browser_session import BrowserSession, CANVAS_PATH, DEMO_PATH
from autoquestion.app import TaskRunner, Status
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.capture.screen import ScreenCapture, WindowsWindowAPI
from autoquestion.llm.fake import FakeLLMProvider
from autoquestion.router import InputRouter
from autoquestion.schemas import VisionAnalysisResult, format_answer
from autoquestion.vision import VisionWorkflow
from test_capture import synthetic_image
from test_vision import vision_payload
from test_idle_navigation import NavigationProbe


class NativeWindowSmoke(unittest.TestCase):
    def test_real_hwnd_pid_focus_dom_canvas_other_window_dom(self):
        browser = BrowserSession()
        self.addCleanup(browser.close)
        browser.start()
        api = WindowsWindowAPI()
        windows = api.browser_windows(browser._process_id)
        self.assertEqual(len(windows), 1)
        hwnd = windows[0]
        api.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        api.user32.SetForegroundWindow.restype = wintypes.BOOL
        def foreground(handle):
            api.user32.SetForegroundWindow(handle)
            # SetForegroundWindow 跨输入队列激活可异步完成，先等待正常交接。
            deadline = time.monotonic() + 1
            while api.foreground() != handle and time.monotonic() < deadline:
                time.sleep(0.05)
            if api.foreground() != handle:
                # 仅测试夹具：对自建/本次 Chromium 窗口临时关联输入线程。
                # 生产代码不切换焦点；不对用户的其他前台进程进行此操作。
                pid = wintypes.DWORD()
                foreground_thread = api.user32.GetWindowThreadProcessId(api.foreground(), ctypes.byref(pid))
                kernel = ctypes.WinDLL('kernel32')
                kernel.GetCurrentThreadId.restype = wintypes.DWORD
                kernel.GetCurrentProcessId.restype = wintypes.DWORD
                self.assertIn(pid.value, (browser._process_id, kernel.GetCurrentProcessId()))
                current_thread = kernel.GetCurrentThreadId()
                api.user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
                api.user32.AttachThreadInput.restype = wintypes.BOOL
                attached = api.user32.AttachThreadInput(current_thread, foreground_thread, True)
                try:
                    api.user32.SetForegroundWindow(handle)
                finally:
                    if attached:
                        api.user32.AttachThreadInput(current_thread, foreground_thread, False)
            deadline = time.monotonic() + 5
            while api.foreground() != handle and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(api.foreground(), handle, '测试窗口未获得焦点；没有读取其他窗口或截图')
        foreground(hwnd)
        capture = ScreenCapture()
        capture.capture = Mock(return_value=synthetic_image())
        vision_provider = Mock(supports_vision=True)
        vision_provider.analyze_image.return_value = VisionAnalysisResult.model_validate(vision_payload(False))
        text_provider = FakeLLMProvider()
        answers = []
        router = InputRouter(capture, browser, lambda question, stop: answers.append(text_provider.answer_question(question)),
                             VisionWorkflow(capture, lambda: vision_provider, lambda status: None), lambda status: None)
        runner = TaskRunner(prepare=router.prepare, prepare_status=Status.ROUTING,
                            clock=lambda: 100 + runner.trigger_count)
        self.addCleanup(runner.close)
        def press_f8():
            with self.assertLogs('autoquestion', level='INFO') as logs:
                self.assertTrue(runner.trigger())
                runner._worker.join(10)
                self.assertFalse(runner._worker.is_alive())
            self.assertEqual(runner.state, Status.READY)
            return '\n'.join(logs.output)
        probe = NavigationProbe(browser)
        with patch('autoquestion.capture.screen.mss.MSS', side_effect=AssertionError('禁止真实截图')):
            for number, expected in enumerate(('答案：A', '答案：木星', '答案：Python、C、Java', '答案：正确')):
                self.assertIn('Input: DOM', press_f8())
                self.assertEqual(format_answer(answers[-1]), expected)
                self.assertEqual(browser._call(lambda: browser._adapter.page.locator('input:checked').count()), 0)
                if number < 3:
                    browser._call(lambda: browser._adapter.page.get_by_role('button', name='下一题').click())
            self.assertEqual(len(answers), 4)
            capture.capture.assert_not_called()
            self.assertTrue(probe.click_while_idle('打开 Canvas 测试题'))
            self.assertEqual(probe.payload['url'], CANVAS_PATH.as_uri())
            self.assertEqual(probe.payload['ready'], 'complete')
            self.assertEqual(probe.payload['drawn'], ['太阳系中最大的行星是？', '木星', '地球', '火星', '金星'])
            self.assertEqual(probe.payload['bands'], [True] * 5)
            self.assertFalse(probe.errors)
            with self.assertRaises(BrowserExtractionError):
                browser.extract_question()
            output = press_f8()
            self.assertIn('Input: DOM unavailable', output)
            self.assertIn('Fallback: VISION', output)
            self.assertEqual(vision_provider.analyze_image.call_count, 1)
            api.user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
            api.user32.CreateWindowExW.restype = wintypes.HWND
            api.user32.DestroyWindow.argtypes = [wintypes.HWND]
            other = api.user32.CreateWindowExW(0, 'STATIC', 'AutoQuestion local test window',
                                               0x10CF0000, 50, 50, 500, 300, None, None, None, None)
            self.assertTrue(other)
            self.addCleanup(lambda: api.user32.DestroyWindow(other))
            foreground(other)
            self.assertIn('Input: VISION', press_f8())
            self.assertEqual(vision_provider.analyze_image.call_count, 2)
            self.assertEqual(capture.capture.call_args.args[0].hwnd, other)
            self.assertTrue(probe.click_while_idle('返回 DOM 测试题'))
            self.assertEqual(probe.payload['url'], DEMO_PATH.as_uri())
            foreground(hwnd)
            self.assertIn('Input: DOM', press_f8())
            self.assertEqual(len(answers), 5)
            self.assertEqual(capture.capture.call_count, 2)
            self.assertEqual(vision_provider.analyze_image.call_count, 2)


if __name__ == '__main__':
    unittest.main()
