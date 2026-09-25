"""SDK 使用内存 MockTransport；所有请求都留在当前进程。"""
from pathlib import Path
import json
import logging
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from pydantic import SecretStr
from autoquestion.config import Config, ConfigError, LLMConfig, load_config, load_llm_config
from autoquestion.demo import make_demo_callback
from autoquestion.app import TaskRunner, Status
from autoquestion.llm.base import LLMProviderError, LLMResponseParseError
from autoquestion.llm.fake import FakeLLMProvider, demo_question
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from autoquestion.llm.parsing import parse_answer_response
from autoquestion.schemas import AnswerValidationError, Question
from test_core import wait_until
from test_schemas import sample_question, answer_data


def config():
    return LLMConfig(SecretStr('test-api-key'), 'https://example.invalid/v1', 'test-model')


def completion(content, finish_reason='stop', refusal=None):
    return {'id': 'test-response', 'object': 'chat.completion', 'created': 0,
            'model': 'test-model', 'choices': [{'index': 0, 'finish_reason': finish_reason,
            'message': {'role': 'assistant', 'content': content, 'refusal': refusal}}]}


class LLMConfigTests(unittest.TestCase):
    def test_fake_default_ignores_missing_api_config(self):
        self.assertEqual(load_config({}).llm_provider, 'fake')
        with self.assertRaisesRegex(ConfigError, 'LLM_API_KEY'):
            load_llm_config({})

    def test_load_config_and_secret_repr(self):
        value = load_llm_config({'LLM_API_KEY': 'test-api-key',
            'LLM_BASE_URL': 'https://example.invalid/v1', 'LLM_MODEL': 'test-model',
            'LLM_SUPPORTS_VISION': 'true', 'LLM_TIMEOUT_SECONDS': '10'})
        self.assertTrue(value.supports_vision)
        self.assertEqual(value.timeout_seconds, 10)
        self.assertNotIn('test-api-key', repr(value))
        self.assertNotIn('test-api-key', str(value.api_key))

    def test_invalid_api_config_is_safe(self):
        valid = {'LLM_API_KEY': 'test-api-key', 'LLM_BASE_URL': 'https://example.invalid/v1',
                 'LLM_MODEL': 'test-model'}
        for change in ({'LLM_API_KEY': ''}, {'LLM_MODEL': ''}, {'LLM_BASE_URL': ''},
                       {'LLM_BASE_URL': 'https://user:private-value@example.invalid'},
                       {'LLM_BASE_URL': 'https://example.invalid?key=private-value'},
                       {'LLM_BASE_URL': 'https://example.invalid:bad/v1'},
                       {'LLM_TIMEOUT_SECONDS': 'nan'}, {'LLM_TIMEOUT_SECONDS': 'inf'},
                       {'LLM_TIMEOUT_SECONDS': '0'}, {'LLM_TIMEOUT_SECONDS': 'private-value'},
                       {'LLM_SUPPORTS_VISION': 'private-value'}):
            with self.subTest(change=change), self.assertRaises(ConfigError) as error:
                load_llm_config(valid | change)
            self.assertNotIn('private-value', str(error.exception))
        with self.assertRaises(ConfigError):
            load_config({'LLM_PROVIDER': 'unknown'})


class ParsingTests(unittest.TestCase):
    def test_plain_fenced_and_short_wrapped_json(self):
        content = json.dumps(answer_data(), ensure_ascii=False)
        for text in (content, f'```json\n{content}\n```', f'```\n{content}\n```',
                     f'结果如下：\n{content}\n以上是答案。'):
            with self.subTest(text=text):
                self.assertEqual(parse_answer_response(text, sample_question()).selected_index, 10)

    def test_unlabeled_answer(self):
        result = parse_answer_response(json.dumps(answer_data(selected_label=None)), sample_question(None))
        self.assertIsNone(result.selected_label)

    def test_invalid_ambiguous_or_nonstandard_json(self):
        valid = json.dumps(answer_data())
        for text in ('not json', '', None, '{}', valid + valid, '[' + valid + ']',
                     '{"selected_index": 10, "selected_index": 20}',
                     valid.replace('0.99', 'NaN'), valid.replace('0.99', 'Infinity'),
                     'x' * 201 + valid, 'x' * 32001, '{broken ' + valid,
                     valid.replace('0.99', '1.5'), valid.replace('0.99', '"0.99"')):
            with self.subTest(text=str(text)[:30]), self.assertRaises(LLMResponseParseError):
                parse_answer_response(text, sample_question())

    def test_schema_errors_do_not_expose_model_text(self):
        with self.assertRaises(LLMResponseParseError) as error:
            parse_answer_response('{"private-value": "private-value"}', sample_question())
        self.assertNotIn('private-value', str(error.exception))

    def test_consistency_errors_are_not_repaired_silently(self):
        for changes in ({'selected_index': 7}, {'selected_label': 'B'}, {'selected_text': '伦敦'}):
            with self.subTest(changes=changes), self.assertRaises(AnswerValidationError):
                parse_answer_response(json.dumps(answer_data(**changes)), sample_question())


class SDKProviderTests(unittest.TestCase):
    def invoke(self, handler, question=None):
        # SDK 真正序列化请求/解析响应，但 MockTransport 不进行网络 I/O。
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1',
                        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client) as factory:
            result = OpenAICompatibleProvider(config()).answer_question(question or sample_question())
            factory.assert_called_once_with(api_key='test-api-key', base_url='https://example.invalid/v1',
                                             timeout=30.0, max_retries=0)
        self.assertTrue(client.is_closed())
        return result

    def test_real_sdk_text_request_and_response(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(str(request.url), 'https://example.invalid/v1/chat/completions')
            body = json.loads(request.content)
            self.assertEqual(body['model'], 'test-model')
            self.assertNotIn('response_format', body)
            self.assertNotIn('image_url', str(body))
            self.assertEqual(body['messages'][0]['role'], 'system')
            self.assertIn('null', body['messages'][0]['content'])
            self.assertEqual(json.loads(body['messages'][1]['content']), sample_question().model_dump(mode='json'))
            return httpx.Response(200, json=completion(json.dumps(answer_data())))
        self.assertEqual(self.invoke(handler).selected_text, '巴黎')
        self.assertEqual(len(requests), 1)

    def test_sdk_unlabeled_answer(self):
        answer = self.invoke(lambda request: httpx.Response(200, json=completion(
            json.dumps(answer_data(selected_label=None)))), sample_question(None))
        self.assertIsNone(answer.selected_label)

    def test_http_failures_are_safe_and_not_retried(self):
        for status in (401, 403, 429, 500):
            calls = []
            def handler(request):
                calls.append(1)
                return httpx.Response(status, json={'error': {'message': 'private-value'}})
            with self.subTest(status=status), self.assertRaises(LLMProviderError) as error:
                self.invoke(handler)
            self.assertNotIn('private-value', str(error.exception))
            self.assertNotIn('test-api-key', str(error.exception))
            self.assertEqual(len(calls), 1)

    def test_timeout_and_connection_errors(self):
        for error_type, message in ((httpx.ReadTimeout, '超时'), (httpx.ConnectError, '连接')):
            def handler(request):
                raise error_type('private-value', request=request)
            with self.subTest(error=error_type), self.assertRaisesRegex(LLMProviderError, message) as error:
                self.invoke(handler)
            self.assertNotIn('private-value', str(error.exception))

    def test_missing_truncated_refused_or_malformed_response(self):
        valid = json.dumps(answer_data())
        for body in ({'choices': []}, completion(valid, 'length'), completion(valid, refusal='private-value'),
                     completion(None), completion('invalid JSON'),
                     {'choices': [{'finish_reason': 'stop', 'message': None}]},
                     {'choices': [None]}):
            with self.subTest(body=body), self.assertRaises(LLMResponseParseError):
                self.invoke(lambda request: httpx.Response(200, json=body))

    def test_unsupported_question_never_creates_client(self):
        with patch('autoquestion.llm.openai_compatible.OpenAI') as client:
            with self.assertRaises(LLMProviderError):
                OpenAICompatibleProvider(config()).answer_question(
                    Question(question_text='描述题', question_type='short_answer'))
            client.assert_not_called()

    def test_sdk_debug_logging_is_suppressed(self):
        loggers = [logging.getLogger(name) for name in ('openai', 'httpx', 'httpcore')]
        saved = [(logger, logger.level, logger.handlers[:], logger.propagate) for logger in loggers]
        try:
            for logger in loggers:
                logger.setLevel(logging.DEBUG)
            with self.assertLogs('autoquestion', level='DEBUG') as logs:
                self.invoke(lambda request: httpx.Response(200, json=completion(json.dumps(answer_data()))))
            self.assertNotIn('test-api-key', '\n'.join(logs.output))
            self.assertIn('validation passed', '\n'.join(logs.output))
            for logger in loggers:
                self.assertFalse(logger.propagate)
        finally:
            for logger, level, handlers, propagate in saved:
                logger.setLevel(level)
                logger.handlers = handlers
                logger.propagate = propagate


class FakeIntegrationTests(unittest.TestCase):
    def test_fake_provider_chain(self):
        self.assertEqual(FakeLLMProvider().answer_question(demo_question()).selected_text, '巴黎')
        with self.assertRaises(LLMProviderError):
            FakeLLMProvider().answer_question(sample_question())

    def test_callback_displays_answer_offline(self):
        with patch('socket.socket.connect', side_effect=AssertionError('Network forbidden')):
            with self.assertLogs('autoquestion', level='INFO') as logs:
                make_demo_callback(Config())(threading.Event())
        text = '\n'.join(logs.output)
        self.assertIn('法国的首都是哪里', text)
        self.assertIn('答案：A', text)
        self.assertIn('99%', text)

    def test_provider_error_then_next_trigger_succeeds(self):
        callback = make_demo_callback(Config())
        now = [0.0]
        runner = TaskRunner(callback, clock=lambda: now[0])
        self.addCleanup(runner.close)
        with patch.object(FakeLLMProvider, 'answer_question', side_effect=LLMProviderError('LLM API 请求超时。')):
            with self.assertLogs('autoquestion', level='INFO') as logs:
                runner.trigger()
                wait_until(lambda: runner.state == Status.READY)
        self.assertIn('Status: ERROR', '\n'.join(logs.output))
        now[0] = 1.0
        with self.assertLogs('autoquestion', level='INFO') as logs:
            runner.trigger()
            wait_until(lambda: runner.state == Status.READY)
        self.assertIn('答案：A', '\n'.join(logs.output))

    def test_missing_api_key_is_recoverable(self):
        runner = TaskRunner(make_demo_callback(Config(llm_provider='openai')))
        self.addCleanup(runner.close)
        with patch.dict('os.environ', {}, clear=True):
            with self.assertLogs('autoquestion', level='INFO') as logs:
                runner.trigger()
                wait_until(lambda: runner.state == Status.READY)
        self.assertIn('LLM_API_KEY 未配置', '\n'.join(logs.output))

    def test_stopped_callback_does_not_invoke_provider(self):
        stop = threading.Event()
        stop.set()
        with patch.object(FakeLLMProvider, 'answer_question') as call:
            make_demo_callback(Config())(stop)
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
