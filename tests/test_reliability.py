"""M11: real SDK over memory transport, schema edges and native lifecycle."""
from pathlib import Path
import json
import os
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from autoquestion.app import TaskRunner, Status, main
from autoquestion.browser_session import BrowserSession
from autoquestion.config import Config, ConfigError, load_llm_config
from autoquestion.hotkeys import WindowsHotkeys
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from autoquestion.router import InputRouter
from autoquestion.schemas import Question, Option, AnswerResult, SourceType, format_answer, validate_answer_against_question
from autoquestion.vision import VisionWorkflow
from test_llm import config, completion
from test_schemas import sample_question, answer_data


class ReliabilityTests(unittest.TestCase):
    def test_actual_sdk_errors_never_reenter_vision_and_close_client(self):
        for case in (401, 429, 500, 'timeout', 'network', 'json', 'answer'):
            with self.subTest(case=case):
                calls = []
                def handler(request):
                    calls.append(1)
                    if case == 'timeout':
                        raise httpx.ReadTimeout('PRIVATE_RESPONSE', request=request)
                    if case == 'network':
                        raise httpx.ConnectError('PRIVATE_RESPONSE', request=request)
                    if isinstance(case, int):
                        return httpx.Response(case, json={'error': {'message': 'PRIVATE_RESPONSE'}})
                    content = 'PRIVATE_RESPONSE' if case == 'json' else json.dumps(answer_data(selected_text='PRIVATE_RESPONSE'))
                    return httpx.Response(200, json=completion(content))
                client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1',
                                max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
                self.addCleanup(client.close)
                provider = OpenAICompatibleProvider(config())
                capture, browser = Mock(), Mock()
                question = sample_question().model_copy(update={'source_type': SourceType.DOM})
                browser.extract_for_target.return_value = question
                report = lambda status: runner.update_status(status)
                vision_provider = Mock(supports_vision=True)
                router = InputRouter(capture, browser, lambda q, stop: provider.answer_question(q),
                                     VisionWorkflow(capture, lambda: vision_provider, report), report)
                runner = TaskRunner(prepare=router.prepare, prepare_status=Status.ROUTING)
                try:
                    with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client), self.assertLogs('autoquestion', 'DEBUG') as logs:
                        self.assertTrue(runner.trigger())
                        runner._worker.join(10)
                    self.assertFalse(runner._worker.is_alive())
                    self.assertEqual(runner.state, Status.READY)
                    output = '\n'.join(logs.output)
                    self.assertIn('Status: ERROR', output)
                    for private in ('PRIVATE_RESPONSE', 'test-api-key', 'Fallback:'):
                        self.assertNotIn(private, output)
                    capture.capture.assert_not_called()
                    vision_provider.analyze_image.assert_not_called()
                    self.assertEqual(len(calls), 1)
                    self.assertTrue(client.is_closed())
                finally:
                    runner.close()

    def test_all_missing_provider_settings_reported_together(self):
        with self.assertRaises(ConfigError) as caught:
            load_llm_config({})
        for name in ('LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL'):
            self.assertIn(name, str(caught.exception))

    def test_unicode_long_stem_option_counts_and_confidence_endpoints(self):
        for count in (2, 50):
            for confidence in (0.0, 1.0):
                with self.subTest(count=count, confidence=confidence):
                    question = Question(question_text='中文🌍' * 2000, question_type='single_choice',
                                        options=tuple(Option(index=i, text=f'选项🌍{i}') for i in range(count)))
                    answer = AnswerResult(question_type='single_choice', selected_index=count-1,
                                          selected_text=question.options[-1].text, confidence=confidence, short_reason='边界测试')
                    validated = validate_answer_against_question(Question.model_validate_json(question.model_dump_json()), answer)
                    self.assertEqual(format_answer(validated), f'答案：选项🌍{count-1}')

    def test_true_false_both_answers_all_wordings_and_labels(self):
        for wording in (('正确', '错误'), ('是', '否'), ('True', 'False')):
            for labels in ((None, None), ('A', 'B')):
                for selected in (0, 1):
                    with self.subTest(wording=wording, labels=labels, selected=selected):
                        question = Question(question_text='判断题🌍', question_type='true_false',
                                            options=tuple(Option(index=i, label=labels[i], text=wording[i]) for i in (0, 1)))
                        answer = AnswerResult(question_type='true_false', selected_index=selected,
                                              selected_label=labels[selected], selected_text=wording[selected], confidence=1.0, short_reason='测试')
                        self.assertEqual(format_answer(validate_answer_against_question(question, answer)),
                                         '答案：' + (labels[selected] or wording[selected]))

    @unittest.skipUnless(sys.platform == 'win32', 'Windows native lifecycle')
    @unittest.skipIf(os.environ.get('AUTOQUESTION_CI') == '1', 'Local desktop hotkey test')
    def test_three_starts_release_native_hotkeys_browser_and_worker(self):
        for exit_kind in ('esc', 'interrupt', 'error'):
            with self.subTest(exit_kind=exit_kind):
                session = BrowserSession(headless=True)
                self.addCleanup(session.close)
                observed = []
                def listen(hotkeys, runner):
                    observed.append(runner)
                    self.assertTrue(runner.trigger())
                    runner._worker.join(10)
                    self.assertFalse(runner._worker.is_alive())
                    self.assertEqual(runner.state, Status.READY)
                    if exit_kind == 'interrupt':
                        raise KeyboardInterrupt()
                    if exit_kind == 'error':
                        raise RuntimeError('PRIVATE_EXIT')
                    runner.stop()
                with (patch('autoquestion.app.load_config', return_value=Config(input_mode='dom')),
                     patch('autoquestion.browser_session.BrowserSession', return_value=session),
                     patch.object(WindowsHotkeys, 'listen', listen), self.assertLogs('autoquestion', 'DEBUG') as logs):
                    code = main([])
                self.assertEqual(code, 1 if exit_kind == 'error' else 0)
                self.assertEqual(len(observed), 1)
                self.assertEqual(observed[0].state, Status.STOPPED)
                self.assertFalse(session._thread.is_alive())
                self.assertTrue(session._closed)
                self.assertNotIn('PRIVATE_EXIT', '\n'.join(logs.output))
                with WindowsHotkeys(Config()):
                    pass
