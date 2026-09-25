"""本地 Chromium → 原有 Provider → TaskRunner；不访问真实 API。"""
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from autoquestion.app import TaskRunner, Status, main
from autoquestion.browser_session import BrowserSession
from autoquestion.capture.browser import BrowserExtractionError
from autoquestion.config import Config, load_config
from autoquestion.dom import make_dom_callback
from autoquestion.llm.base import LLMProviderError
from autoquestion.llm.fake import FakeLLMProvider, demo_question
from autoquestion.schemas import SourceType
from test_llm import config, completion


class DOMWorkflowTests(unittest.TestCase):
    def run_job(self, runner):
        self.assertTrue(runner.trigger())
        runner._worker.join(20)
        self.assertFalse(runner._worker.is_alive())
        self.assertEqual(runner.state, Status.READY)

    def test_real_browser_fake_answers_for_all_four_questions(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        browser.start()
        runner = TaskRunner(clock=lambda: 100 + runner.trigger_count)
        runner._callback = make_dom_callback(Config(input_mode='dom'), browser, runner.update_status)
        self.addCleanup(runner.close)
        for expected in ('答案：A', '答案：木星', '答案：Python、C、Java', '答案：正确'):
            with self.subTest(expected=expected), self.assertLogs('autoquestion', level='INFO') as logs:
                self.run_job(runner)
            output = '\n'.join(logs.output)
            self.assertIn(expected, output)
            self.assertIn('Status: EXTRACTING', output)
            self.assertNotIn('ERROR', output)
            self.assertIn('ANALYZING', output)
            self.assertEqual(browser._call(lambda: browser._adapter.page.locator('input:checked').count()), 0)
            if expected != '答案：正确':
                browser._call(lambda: browser._adapter.page.get_by_role('button', name='下一题').click())

    def test_extraction_and_provider_failures_recover_without_vision(self):
        question = demo_question().model_copy(update={'source_type': SourceType.DOM})
        browser = Mock()
        browser.extract_question.side_effect = [BrowserExtractionError('没有可识别题目'), question, question]
        runner = TaskRunner(clock=lambda: 100 + runner.trigger_count)
        runner._callback = make_dom_callback(Config(input_mode='dom'), browser, runner.update_status)
        self.addCleanup(runner.close)
        with patch('autoquestion.vision.make_vision_prepare') as vision:
            with self.assertLogs('autoquestion') as logs:
                self.run_job(runner)
            self.assertIn('Status: ERROR', '\n'.join(logs.output))
            with patch.object(FakeLLMProvider, 'answer_question', side_effect=LLMProviderError('测试 API 失败')):
                with self.assertLogs('autoquestion') as logs:
                    self.run_job(runner)
                self.assertIn('Status: ERROR', '\n'.join(logs.output))
            with self.assertLogs('autoquestion') as logs:
                self.run_job(runner)
            self.assertIn('答案：A', '\n'.join(logs.output))
            vision.assert_not_called()

    def test_busy_and_stop_do_not_start_second_extraction_or_provider(self):
        entered, release = threading.Event(), threading.Event()
        browser = Mock()
        def extract():
            entered.set()
            release.wait(5)
            return demo_question().model_copy(update={'source_type': SourceType.DOM})
        browser.extract_question.side_effect = extract
        runner = TaskRunner()
        runner._callback = make_dom_callback(Config(input_mode='dom'), browser, runner.update_status)
        self.addCleanup(runner.close)
        self.addCleanup(release.set)
        with patch.object(FakeLLMProvider, 'answer_question') as provider:
            self.assertTrue(runner.trigger())
            self.assertTrue(entered.wait(5))
            self.assertFalse(runner.trigger())
            self.assertEqual(runner.state, Status.BUSY)
            runner.stop()
            release.set()
            runner.close()
            provider.assert_not_called()
        browser.extract_question.assert_called_once()
        self.assertEqual(runner.state, Status.STOPPED)

    def test_real_dom_question_through_existing_sdk_has_only_structured_text(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        browser.start()
        question = browser.extract_question()
        requests = []
        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(json.loads(body['messages'][1]['content']), question.model_dump(mode='json'))
            self.assertNotIn('image_url', str(body))
            return httpx.Response(200, json=completion(FakeLLMProvider().answer_question(question).model_dump_json()))
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        statuses = []
        with patch('autoquestion.dom.load_llm_config', return_value=config()), \
             patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client), \
             self.assertLogs('autoquestion') as logs:
            make_dom_callback(Config(input_mode='dom', llm_provider='openai'), browser, statuses.append)(threading.Event())
        self.assertEqual(statuses, ['EXTRACTING', 'ANALYZING'])
        self.assertEqual(len(requests), 1)
        self.assertIn('答案：A', '\n'.join(logs.output))

    def test_main_dom_owns_and_closes_browser(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        def listen(runner):
            self.run_job(runner)
            runner.stop()
        with patch('autoquestion.app.load_config', return_value=Config(input_mode='dom')), \
             patch('autoquestion.browser_session.BrowserSession', return_value=browser), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys:
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listen
            self.assertEqual(main([]), 0)
        self.assertTrue(browser._closed)

    def test_default_mode_retained_and_dom_explicit(self):
        self.assertEqual(load_config({}).input_mode, 'vision')
        self.assertEqual(load_config({'INPUT_MODE': 'dom'}).input_mode, 'dom')
