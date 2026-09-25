"""路由调用次数与真实浏览器匹配边界；像素/API 全部使用合成数据。"""
from dataclasses import replace
import logging
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from autoquestion.app import Status, TaskRunner, main
from autoquestion.browser_session import BrowserSession, CANVAS_PATH, DEMO_PATH
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.capture.screen import ScreenCapture, CaptureError, WindowTarget
from autoquestion.config import Config, load_config
from autoquestion.dom import answer_dom_question
from autoquestion.llm.base import BaseLLMProvider, LLMProviderError, LLMResponseParseError
from autoquestion.llm.fake import FakeLLMProvider, demo_question
from autoquestion.router import InputRouter
from autoquestion.schemas import AnswerValidationError, SourceType, VisionAnalysisResult
from autoquestion.vision import VisionWorkflow
from test_capture import synthetic_image
from test_vision import vision_payload


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.target = WindowTarget(123, 456, 0, 0, 900, 700, 'PRIVATE_TITLE')
        self.capture = Mock(spec=ScreenCapture)
        self.capture.snapshot_target.return_value = self.target
        self.capture.capture.return_value = synthetic_image()
        self.browser = Mock(spec=BrowserSession)
        self.question = demo_question().model_copy(update={'source_type': SourceType.DOM})
        self.browser.extract_for_target.return_value = self.question
        self.provider = Mock(spec=BaseLLMProvider)
        self.provider.supports_vision = True
        self.provider.answer_question.return_value = FakeLLMProvider().answer_question(self.question)
        self.provider.analyze_image.return_value = VisionAnalysisResult.model_validate(vision_payload())
        self.provider_patch = patch('autoquestion.dom.FakeLLMProvider', return_value=self.provider)
        self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        report = lambda status: self.runner.update_status(status)
        vision = VisionWorkflow(self.capture, lambda: self.provider, report)
        self.router = InputRouter(self.capture, self.browser,
            lambda question, stop: answer_dom_question(Config(input_mode='auto'), question, stop, report), vision, report)
        self.runner = TaskRunner(prepare=self.router.prepare, prepare_status=Status.ROUTING,
                                 clock=lambda: 100 + self.runner.trigger_count)
        self.addCleanup(self.runner.close)

    def run_job(self):
        with self.assertLogs('autoquestion', level='DEBUG') as logs:
            self.assertTrue(self.runner.trigger())
            self.runner._worker.join(10)
            self.assertFalse(self.runner._worker.is_alive())
        self.assertEqual(self.runner.state, Status.READY)
        text = '\n'.join(logs.output)
        self.assertNotIn('PRIVATE_TITLE', text)
        return text

    def assert_no_vision(self):
        self.capture.capture.assert_not_called()
        self.provider.analyze_image.assert_not_called()

    def test_managed_dom_success_no_screenshot_one_answer(self):
        text = self.run_job()
        self.assertIn('Input: DOM', text)
        self.assertEqual(text.count('答案：'), 1)
        self.assertNotIn('CAPTURING', text)
        self.assert_no_vision()
        self.provider.answer_question.assert_called_once_with(self.question)

    def test_non_browser_never_reads_background_dom(self):
        self.browser.extract_for_target.side_effect = BrowserExtractionError('不是受管理浏览器')
        self.assertIn('Input: VISION', self.run_job())
        self.capture.capture.assert_called_once_with(self.target)
        self.provider.analyze_image.assert_called_once()
        self.provider.answer_question.assert_not_called()

    def test_no_managed_session_uses_vision(self):
        self.router.browser = None
        self.run_job()
        self.browser.extract_for_target.assert_not_called()
        self.capture.capture.assert_called_once_with(self.target)
        self.provider.analyze_image.assert_called_once()

    def test_acquisition_errors_each_make_one_capture_and_vision_request(self):
        for reason in ('无题', 'Page closed', 'Browser disconnected', 'Canvas'):
            with self.subTest(reason=reason):
                self.capture.capture.reset_mock()
                self.provider.analyze_image.reset_mock()
                self.browser.extract_for_target.side_effect = BrowserExtractionError(reason)
                self.assertIn('Fallback: VISION', self.run_job())
                self.capture.capture.assert_called_once_with(self.target)
                self.provider.analyze_image.assert_called_once()
        self.provider.answer_question.assert_not_called()

    def test_malformed_dom_revalidated_before_text(self):
        for value in (None, {}, self.question.model_copy(update={'question_text': ' '}),
                      self.question.model_copy(update={'options': ()}),
                      self.question.model_copy(update={'source_type': SourceType.MANUAL}),
                      self.question.model_copy(update={'question_type': 'multiple_choice', 'options': ()})):
            with self.subTest(value=type(value)):
                self.capture.capture.reset_mock()
                self.provider.analyze_image.reset_mock()
                self.browser.extract_for_target.return_value = value
                self.run_job()
                self.capture.capture.assert_called_once_with(self.target)
                self.provider.analyze_image.assert_called_once()
        self.provider.answer_question.assert_not_called()

    def test_text_auth_timeout_network_rate_limit_json_and_validation_never_fallback(self):
        for error in (LLMProviderError('authentication failed'), LLMProviderError('timeout'),
                      LLMProviderError('network'), LLMProviderError('rate limit'),
                      LLMResponseParseError('invalid JSON'), AnswerValidationError('invalid AnswerResult')):
            with self.subTest(error=str(error)):
                self.provider.answer_question.side_effect = error
                text = self.run_job()
                self.assertIn('Status: ERROR', text)
                self.assertNotIn('Fallback:', text)
                self.assert_no_vision()

    def test_actual_answer_consistency_error_never_fallback(self):
        self.provider.answer_question.return_value = self.provider.answer_question.return_value.model_copy(update={'selected_text': '错误文本'})
        self.assertIn('Status: ERROR', self.run_job())
        self.assert_no_vision()

    def test_vision_disabled_prevents_pixels_and_recovers(self):
        self.router.browser = None
        self.provider.supports_vision = False
        self.assertIn('not configured for vision', self.run_job())
        self.assert_no_vision()

    def test_vision_api_error_one_attempt_and_ready(self):
        self.router.browser = None
        self.provider.analyze_image.side_effect = LLMProviderError('Vision API error')
        self.assertIn('Status: ERROR', self.run_job())
        self.capture.capture.assert_called_once_with(self.target)
        self.provider.analyze_image.assert_called_once()

    def test_dom_vision_dom_can_switch_without_restart(self):
        self.run_job()
        self.browser.extract_for_target.side_effect = BrowserExtractionError('其他窗口')
        self.run_job()
        self.browser.extract_for_target.side_effect = None
        self.run_job()
        self.assertEqual(self.provider.answer_question.call_count, 2)
        self.assertEqual(self.capture.capture.call_count, 1)
        self.assertEqual(self.provider.analyze_image.call_count, 1)

    def test_busy_and_exit_during_analysis(self):
        entered, release = threading.Event(), threading.Event()
        answer = self.provider.answer_question.return_value
        def slow(question):
            entered.set()
            release.wait(5)
            return answer
        self.provider.answer_question.side_effect = slow
        self.addCleanup(release.set)
        with self.assertLogs('autoquestion') as logs:
            self.assertTrue(self.runner.trigger())
            self.assertTrue(entered.wait(3))
            for _ in range(10):
                self.assertFalse(self.runner.trigger())
            self.assertEqual(self.runner.state, Status.BUSY)
            self.runner.stop()
            release.set()
            self.runner.close()
        self.capture.snapshot_target.assert_called_once()
        self.provider.answer_question.assert_called_once()
        self.assert_no_vision()
        self.assertNotIn('答案：', '\n'.join(logs.output))

    def test_snapshot_precedes_logs_and_fallback_keeps_original_target(self):
        order = []
        self.capture.snapshot_target.side_effect = lambda: order.append('snapshot') or self.target
        class Recorder(logging.Handler):
            def emit(self, record):
                order.append('log')
        logger = logging.getLogger('autoquestion')
        handler = Recorder()
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            self.router.browser = None
            self.runner.trigger()
            self.runner._worker.join(5)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertEqual(order[0], 'snapshot')
        self.capture.snapshot_target.assert_called_once()
        self.capture.capture.assert_called_once_with(self.target)
        self.assertNotIn('PRIVATE_TITLE', repr(self.target))

    def test_target_changed_during_dom_ends_without_fallback(self):
        self.browser.extract_for_target.side_effect = CaptureError('目标已切换')
        self.assertIn('Status: ERROR', self.run_job())
        self.assert_no_vision()

    def test_target_closed_before_fallback_never_calls_vision(self):
        self.router.browser = None
        self.capture.capture.side_effect = CaptureError('目标已关闭')
        self.assertIn('Status: ERROR', self.run_job())
        self.provider.analyze_image.assert_not_called()
        self.capture.snapshot_target.assert_called_once()

    def test_unlabeled_dom_and_vision_keep_source_and_null_labels(self):
        self.question = self.question.model_copy(update={'options': tuple(o.model_copy(update={'label': None}) for o in self.question.options)})
        self.browser.extract_for_target.return_value = self.question
        self.provider.answer_question.return_value = self.provider.answer_question.return_value.model_copy(update={'selected_label': None})
        self.assertIn('答案：巴黎', self.run_job())
        self.assertEqual(self.provider.answer_question.call_args.args[0].source_type, SourceType.DOM)
        self.router.browser = None
        result = VisionAnalysisResult.model_validate(vision_payload(False))
        self.provider.analyze_image.return_value = result
        self.assertIn('答案：巴黎', self.run_job())
        self.assertEqual(result.question.source_type, SourceType.VISION)
        self.assertIsNone(result.answer.selected_label)

    def test_auto_config_explicit_default_compatible(self):
        self.assertEqual(load_config({'INPUT_MODE': 'auto'}).input_mode, 'auto')
        self.assertEqual(load_config({}).input_mode, 'vision')

    def test_main_auto_startup_failure_preserves_vision_and_cleanup(self):
        failed_browser = Mock(spec=BrowserSession)
        failed_browser.start.side_effect = BrowserExtractionError('runtime missing')
        def listen(runner):
            self.assertTrue(runner.trigger())
            runner._worker.join(5)
            self.assertEqual(runner.state, Status.READY)
            runner.stop()
        with patch('autoquestion.app.load_config', return_value=Config(input_mode='auto', llm_provider='openai')), \
             patch('autoquestion.browser_session.BrowserSession', return_value=failed_browser), \
             patch('autoquestion.router.ScreenCapture', return_value=self.capture), \
             patch('autoquestion.router.vision_provider', return_value=self.provider), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys:
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listen
            self.assertEqual(main(['--open-demo']), 0)
        failed_browser.close.assert_called_once()
        self.capture.capture.assert_called_once_with(self.target)
        self.provider.analyze_image.assert_called_once()

    def test_main_auto_routes_to_dom_and_closes_session(self):
        def listen(runner):
            self.assertTrue(runner.trigger())
            runner._worker.join(5)
            self.assertEqual(runner.state, Status.READY)
            runner.stop()
        with patch('autoquestion.app.load_config', return_value=Config(input_mode='auto')), \
             patch('autoquestion.browser_session.BrowserSession', return_value=self.browser), \
             patch('autoquestion.router.ScreenCapture', return_value=self.capture), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys:
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listen
            self.assertEqual(main(['--open-demo']), 0)
        self.browser.close.assert_called_once()
        self.provider.answer_question.assert_called_once()
        self.assert_no_vision()

    def test_stop_during_acquisition_suppresses_fallback(self):
        def acquire(*args):
            self.runner.stop()
            raise BrowserExtractionError('无题')
        self.browser.extract_for_target.side_effect = acquire
        self.assertTrue(self.runner.trigger())
        self.runner._worker.join(5)
        self.assert_no_vision()
        self.provider.answer_question.assert_not_called()

    def test_unexpected_acquisition_bug_is_not_silently_fallback(self):
        self.browser.extract_for_target.side_effect = RuntimeError('PRIVATE_TITLE')
        self.assertIn('Status: ERROR', self.run_job())
        self.assert_no_vision()


class BrowserRoutingTests(unittest.TestCase):
    def setUp(self):
        self.browser = BrowserSession(headless=True)
        self.addCleanup(self.browser.close)
        self.browser.start()
        self.target = WindowTarget(123, self.browser._process_id, 0, 0, 900, 700)

    def test_real_cdp_process_id_and_reject_other_process_before_dom(self):
        self.assertGreater(self.browser._process_id, 0)
        with patch.object(self.browser._adapter, 'extract_question') as extract:
            with self.assertRaises(BrowserExtractionError):
                self.browser.extract_for_target(replace(self.target, process_id=-1), Mock())
            extract.assert_not_called()

    def test_matching_single_window_reads_real_dom_and_canvas_fails(self):
        # 真实 headless Page/CDP；Windows 顶层窗口枚举只在此测试中模拟。
        verify = Mock()
        with patch('autoquestion.browser_session.WindowsWindowAPI') as windows:
            windows.return_value.browser_windows.return_value = [123]
            self.assertEqual(self.browser.extract_for_target(self.target, verify).source_type, SourceType.DOM)
            self.assertEqual(verify.call_count, 2)
            self.browser._call(lambda: self.browser._adapter.page.goto(CANVAS_PATH.as_uri()))
            with self.assertRaises(BrowserExtractionError):
                self.browser.extract_for_target(self.target, verify)
            self.browser._call(lambda: self.browser._adapter.page.goto(DEMO_PATH.as_uri()))
            self.assertEqual(self.browser.extract_for_target(self.target, verify).source_type, SourceType.DOM)

    def test_multiple_windows_or_tabs_reject_before_extraction(self):
        with patch('autoquestion.browser_session.WindowsWindowAPI') as windows, \
             patch.object(self.browser._adapter, 'extract_question') as extract:
            windows.return_value.browser_windows.return_value = [123, 456]
            with self.assertRaises(BrowserExtractionError):
                self.browser.extract_for_target(self.target, Mock())
            windows.return_value.browser_windows.return_value = [123]
            self.browser._call(lambda: self.browser._adapter.page.context.new_page())
            with self.assertRaises(BrowserExtractionError):
                self.browser.extract_for_target(self.target, Mock())
            extract.assert_not_called()

    def test_closed_page_and_disconnected_browser(self):
        self.browser._call(lambda: self.browser._adapter.page.close())
        with self.assertRaises(BrowserExtractionError):
            self.browser.extract_for_target(self.target, Mock())
        self.browser._call(lambda: self.browser._browser.close())
        with self.assertRaises(BrowserExtractionError):
            self.browser.extract_for_target(self.target, Mock())
