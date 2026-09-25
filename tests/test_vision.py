"""Vision 协议和 F8 流程的离线测试；不抓取桌面、不调用模型服务。"""
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import base64
import json
import logging
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from pydantic import ValidationError
from autoquestion.app import TaskRunner, Status, main
from autoquestion.capture.screen import ScreenCapture, CaptureError, WindowTarget
from autoquestion.config import ConfigError, load_config, load_env_file
from autoquestion.llm.base import BaseLLMProvider, LLMProviderError, LLMResponseParseError
from autoquestion.llm.fake import demo_question, FakeLLMProvider
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from autoquestion.llm.parsing import parse_vision_response
from autoquestion.schemas import VisionAnalysisResult, format_answer
from autoquestion.vision import VisionWorkflow
from test_capture import synthetic_image
from test_core import wait_until
from test_llm import completion, config


def vision_payload(labeled=True):
    question = demo_question().model_dump(mode='json')
    question['source_type'] = 'VISION'
    if not labeled:
        for option in question['options']:
            option['label'] = None
    answer = FakeLLMProvider().answer_question(demo_question()).model_dump(mode='json')
    if not labeled:
        answer['selected_label'] = None
    return {'question': question, 'answer': answer}


class VisionSchemaTests(unittest.TestCase):
    def test_labeled_and_unlabeled_results(self):
        for labeled, display in ((True, '答案：A'), (False, '答案：巴黎')):
            with self.subTest(labeled=labeled):
                result = parse_vision_response(json.dumps(vision_payload(labeled)))
                self.assertEqual(format_answer(result.answer), display)
                self.assertEqual(result.answer.selected_text, '巴黎')
                self.assertEqual(result.question.source_type.value, 'VISION')

    def test_fenced_and_wrapped_json(self):
        text = json.dumps(vision_payload())
        for content in (f'```json\n{text}\n```', f'结果：{text}以上。'):
            self.assertEqual(parse_vision_response(content).answer.selected_index, 0)

    def test_invalid_vision_results(self):
        variants = []
        for field, value in (('selected_index', 7), ('selected_text', '伦敦'),
                             ('selected_label', 'B'), ('confidence', 1.1)):
            payload = vision_payload()
            payload['answer'][field] = value
            variants.append(payload)
        payload = vision_payload(False)
        payload['answer']['selected_label'] = 'A'
        variants.append(payload)
        for source in ('MANUAL', 'DOM'):
            payload = vision_payload()
            payload['question']['source_type'] = source
            variants.append(payload)
        payload = vision_payload()
        payload['question']['options'][1]['index'] = 5
        variants.append(payload)
        payload = vision_payload()
        payload['question']['question_type'] = 'multiple_choice'
        payload['answer']['question_type'] = 'multiple_choice'
        variants.append(payload)
        variants.extend([{'question': []}, [vision_payload(), vision_payload()]])
        for payload in variants:
            with self.subTest(payload=payload), self.assertRaises(LLMResponseParseError):
                parse_vision_response(json.dumps(payload))

    def test_no_question_and_invalid_json_are_clear_errors(self):
        with self.assertRaisesRegex(LLMResponseParseError, '无法可靠识别'):
            parse_vision_response('{"error":"unable_to_identify_question"}')
        with self.assertRaises(LLMResponseParseError):
            parse_vision_response('invalid JSON')

    def test_schema_itself_enforces_consistency(self):
        data = vision_payload()
        data['answer']['selected_text'] = 'private-value'
        with self.assertRaises(ValidationError) as error:
            VisionAnalysisResult.model_validate(data)
        self.assertNotIn('private-value', str(error.exception))


class VisionSDKTests(unittest.TestCase):
    def test_one_image_one_request_and_no_sensitive_logs(self):
        image = synthetic_image()
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=completion(json.dumps(vision_payload(False))))
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client):
            with self.assertLogs('autoquestion', level='DEBUG') as logs:
                result = OpenAICompatibleProvider(replace(config(), supports_vision=True)).analyze_image(image)
        self.assertTrue(client.is_closed())
        self.assertEqual(len(requests), 1)
        self.assertEqual(format_answer(result.answer), '答案：巴黎')
        body = requests[0]
        self.assertNotIn('response_format', body)
        self.assertEqual(body['messages'][0]['role'], 'system')
        self.assertIn('label=null', body['messages'][0]['content'])
        parts = body['messages'][1]['content']
        self.assertEqual(len(parts), 2)
        image_url = parts[1]['image_url']['url']
        self.assertTrue(image_url.startswith('data:image/png;base64,'))
        encoded = image_url.split(',', 1)[1]
        self.assertEqual(base64.b64decode(encoded), image.data)
        self.assertNotIn(encoded, '\n'.join(logs.output))
        self.assertNotIn('test-api-key', '\n'.join(logs.output))

    def test_disabled_vision_never_creates_client(self):
        with patch('autoquestion.llm.openai_compatible.OpenAI') as factory:
            with self.assertRaisesRegex(LLMProviderError, 'not configured for vision'):
                OpenAICompatibleProvider(config()).analyze_image(synthetic_image())
            factory.assert_not_called()
        with self.assertRaises(LLMProviderError):
            FakeLLMProvider().analyze_image(synthetic_image())

    def test_api_errors_are_shared_with_text_provider(self):
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(
                            lambda request: httpx.Response(500, json={'error': {'message': 'private-value'}}))))
        with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client):
            with self.assertRaises(LLMProviderError) as error:
                OpenAICompatibleProvider(replace(config(), supports_vision=True)).analyze_image(synthetic_image())
        self.assertNotIn('private-value', str(error.exception))
        self.assertTrue(client.is_closed())


class VisionWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.capture = Mock(spec=ScreenCapture)
        self.capture.snapshot_target.return_value = WindowTarget(123, 456, 0, 0, 100, 100)
        self.capture.capture.return_value = synthetic_image()
        self.provider = Mock(spec=BaseLLMProvider)
        self.provider.supports_vision = True
        self.provider.analyze_image.return_value = VisionAnalysisResult.model_validate(vision_payload())
        self.now = [0.0]
        workflow = VisionWorkflow(self.capture, lambda: self.provider,
                                  lambda status: self.runner.update_status(status))
        self.runner = TaskRunner(prepare=workflow.prepare, clock=lambda: self.now[0])
        self.addCleanup(self.runner.close)

    def trigger_and_wait(self):
        self.assertTrue(self.runner.trigger())
        wait_until(lambda: self.runner.state == Status.READY)

    def test_snapshot_precedes_all_logs_then_five_rounds(self):
        order = []
        self.capture.snapshot_target.side_effect = lambda: order.append('snapshot') or WindowTarget(123, 456, 0, 0, 100, 100)
        class Handler(logging.Handler):
            def emit(self, record):
                order.append(record.getMessage())
        logger = logging.getLogger('autoquestion')
        handler = Handler()
        old_level = logger.level
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        try:
            for number in range(5):
                self.now[0] = number * 0.5
                self.trigger_and_wait()
                self.assertFalse(self.runner.trigger())  # debounce
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertEqual(order[0], 'snapshot')
        self.assertEqual(self.capture.snapshot_target.call_count, 5)
        self.assertEqual(self.capture.capture.call_count, 5)
        self.assertEqual(self.provider.analyze_image.call_count, 5)
        self.assertEqual(order.count('Status: CAPTURING'), 5)
        self.assertEqual(order.count('Status: ANALYZING'), 5)
        self.assertEqual(order.count('Status: READY'), 5)
        self.provider.answer_question.assert_not_called()

    def test_busy_never_snapshots_or_calls_provider_twice(self):
        entered, release = threading.Event(), threading.Event()
        result = self.provider.analyze_image.return_value
        def slow_api(image):
            entered.set()
            release.wait(3)
            return result
        self.provider.analyze_image.side_effect = slow_api
        self.addCleanup(release.set)
        self.runner.trigger()
        self.assertTrue(entered.wait(2))
        for _ in range(20):
            self.assertFalse(self.runner.trigger())
        self.assertEqual(self.runner.state, Status.BUSY)
        self.capture.snapshot_target.assert_called_once()
        self.provider.analyze_image.assert_called_once()
        release.set()
        wait_until(lambda: self.runner.state == Status.READY)

    def test_api_parse_and_capture_errors_recover_for_next_f8(self):
        for error in (LLMProviderError('API timeout'), LLMResponseParseError('Invalid JSON')):
            self.provider.analyze_image.side_effect = error
            self.now[0] += 1
            with self.assertLogs('autoquestion', level='INFO') as logs:
                self.trigger_and_wait()
            self.assertIn('Status: ERROR', '\n'.join(logs.output))
        self.provider.analyze_image.side_effect = None
        self.capture.capture.side_effect = CaptureError('Screenshot failure')
        self.now[0] += 1
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.trigger_and_wait()
        self.assertIn('Screenshot failure', '\n'.join(logs.output))
        self.capture.capture.side_effect = None
        self.now[0] += 1
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.trigger_and_wait()
        self.assertIn('答案：A', '\n'.join(logs.output))

    def test_snapshot_failure_recovers_without_worker(self):
        self.capture.snapshot_target.side_effect = CaptureError('No foreground window')
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.assertFalse(self.runner.trigger())
        self.assertEqual(self.runner.state, Status.READY)
        self.capture.capture.assert_not_called()
        self.provider.analyze_image.assert_not_called()
        self.assertIn('No foreground window', '\n'.join(logs.output))
        self.capture.snapshot_target.side_effect = None
        self.now[0] = 1
        self.trigger_and_wait()

    def test_vision_disabled_prevents_capture_and_api(self):
        self.provider.supports_vision = False
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.trigger_and_wait()
        self.assertIn('not configured for vision', '\n'.join(logs.output))
        self.capture.capture.assert_not_called()
        self.provider.analyze_image.assert_not_called()

    def test_exit_during_api_joins_worker_without_answer_output(self):
        entered, release = threading.Event(), threading.Event()
        result = self.provider.analyze_image.return_value
        def slow_api(image):
            entered.set()
            release.wait(3)
            return result
        self.provider.analyze_image.side_effect = slow_api
        self.addCleanup(release.set)
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.runner.trigger()
            self.assertTrue(entered.wait(2))
            self.runner.stop()
            release.set()
            self.runner.close()
        self.assertEqual(self.runner.state, Status.STOPPED)
        self.assertNotIn('答案：', '\n'.join(logs.output))
        self.assertFalse(any(t.name == 'autoquestion-worker' for t in threading.enumerate()))

    def test_main_selects_vision_flow_and_returns_ready_repeatedly(self):
        def listen(runner):
            for _ in range(2):
                self.assertTrue(runner.trigger())
                wait_until(lambda: runner.state == Status.READY)
                time.sleep(0.45)
            runner.stop()
        with patch.dict('os.environ', {'INPUT_MODE': 'vision', 'LLM_PROVIDER': 'openai'}, clear=True), \
             patch('autoquestion.vision.ScreenCapture', return_value=self.capture), \
             patch('autoquestion.vision.load_llm_config', return_value=replace(config(), supports_vision=True)), \
             patch('autoquestion.vision.OpenAICompatibleProvider', return_value=self.provider), \
             patch('autoquestion.hotkeys.WindowsHotkeys') as hotkeys:
            hotkeys.return_value.__enter__.return_value.listen.side_effect = listen
            with self.assertLogs('autoquestion', level='INFO') as logs:
                self.assertEqual(main([]), 0)
        text = '\n'.join(logs.output)
        self.assertEqual(text.count('答案：A'), 2)
        self.assertIn('Status: STOPPED', text)
        self.assertEqual(self.capture.capture.call_count, 2)


class VisionConfigTests(unittest.TestCase):
    def test_modes_and_max_edge_validation(self):
        self.assertEqual(load_config({}).input_mode, 'vision')
        self.assertEqual(load_config({'INPUT_MODE': 'demo'}).input_mode, 'demo')
        self.assertEqual(load_config({'IMAGE_MAX_EDGE': '3072'}).image_max_edge, 3072)
        for data in ({'INPUT_MODE': 'monitor'}, {'IMAGE_MAX_EDGE': '512'},
                     {'IMAGE_MAX_EDGE': '4097'}, {'IMAGE_MAX_EDGE': 'private-value'}):
            with self.subTest(data=data), self.assertRaises(ConfigError):
                load_config(data)

    def test_explicit_env_file_no_interpolation_environment_wins(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'test-config'
            path.write_text('LLM_API_KEY=test-api-key\nINPUT_MODE=vision\nLLM_MODEL=${PRIVATE}\n', encoding='utf-8')
            with patch.dict('os.environ', {'INPUT_MODE': 'demo'}, clear=True):
                load_env_file(path)
                import os
                self.assertEqual(os.environ['INPUT_MODE'], 'demo')
                self.assertEqual(os.environ['LLM_API_KEY'], 'test-api-key')
                self.assertEqual(os.environ['LLM_MODEL'], '${PRIVATE}')
            self.assertIn('test-api-key', path.read_text())
            with self.assertRaises(ConfigError):
                load_env_file(Path(directory) / 'missing')


if __name__ == '__main__':
    unittest.main()
