"""同屏混合题型：单图单请求、严格逐题对应、原子发布与停止保护。"""
import copy
import json
import logging
from pathlib import Path
import sys
import threading
import unittest
from dataclasses import replace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from autoquestion.capture.screen import ScreenCapture, WindowTarget
from autoquestion.llm.base import BaseLLMProvider, LLMProviderError, LLMResponseParseError
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from autoquestion.llm.parsing import parse_vision_response
from autoquestion.schemas import VisionBatchResult
from autoquestion.vision import VisionWorkflow
from test_capture import synthetic_image
from test_llm import completion, config
from test_vision import vision_payload


def batch_payload():
    single = vision_payload()
    single['question']['question_text'] = '1. 法国的首都？'
    multi = copy.deepcopy(single)
    multi['question'].update(question_text='2. 以下哪些是欧洲城市？', question_type='multiple_choice')
    multi['answer'] = dict(question_type='multiple_choice', selected_indices=[1, 0],
                           selected_labels=['B', 'A'], selected_texts=['伦敦', '巴黎'],
                           confidence=0.9, short_reason='巴黎和伦敦均在欧洲。')
    return {'results': [single, multi]}


def mixed_batch_payload(count=6):
    results = []
    for number in range(count):
        item = copy.deepcopy(batch_payload()['results'][number % 2])
        if number % 3 == 2:
            item['question'].update(question_type='true_false', options=[
                dict(index=0, label=None, text='正确'), dict(index=1, label=None, text='错误')])
            item['answer'] = dict(question_type='true_false', selected_index=1, selected_label=None,
                                  selected_text='错误', confidence=0.8, short_reason='判断题示例理由。')
        item['question']['question_text'] = f'{number + 1}. 混合题型示例 {number + 1}'
        results.append(item)
    return {'results': results}


class VisionBatchTests(unittest.TestCase):
    def test_three_to_six_mixed_questions_including_true_false(self):
        for count in range(3, 7):
            with self.subTest(count=count):
                result = parse_vision_response(json.dumps(mixed_batch_payload(count)))
                self.assertEqual(len(result.results), count)
                self.assertEqual(result.results[2].answer.selected_text, '错误')
                self.assertEqual(result.results[1].answer.selected_texts, ('巴黎', '伦敦'))
                self.assertEqual([r.question.question_text.split('.')[0] for r in result.results],
                                 [str(i) for i in range(1, count + 1)])

    def test_mixed_questions_keep_order_and_each_answer_is_normalized(self):
        result = parse_vision_response(json.dumps(batch_payload()))
        self.assertIsInstance(result, VisionBatchResult)
        self.assertTrue(result.results[0].question.question_text.startswith('1.'))
        self.assertEqual(result.results[0].answer.selected_text, '巴黎')
        self.assertEqual(result.results[1].answer.selected_texts, ('巴黎', '伦敦'))

    def test_empty_over_limit_duplicates_unknown_fields_and_cross_question_answers_rejected(self):
        variants = [{'results': []}, {'results': [vision_payload()] * 11},
                    {'results': [vision_payload(), vision_payload()]},
                    batch_payload() | {'answer': 'unexpected'}]
        data = batch_payload()
        data['results'][1]['answer'] = copy.deepcopy(data['results'][0]['answer'])
        variants.append(data)
        data = batch_payload()
        data['results'][1]['answer']['selected_texts'][1] = 'not-an-option'
        variants.append(data)
        for data in variants:
            with self.subTest(data=data), self.assertRaises(LLMResponseParseError):
                parse_vision_response(json.dumps(data))

    def test_one_image_one_http_request_returns_both_questions(self):
        requests = []
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=completion(json.dumps(batch_payload())))
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client):
            result = OpenAICompatibleProvider(replace(config(), supports_vision=True)).analyze_image(synthetic_image())
        self.assertEqual(len(requests), 1)
        self.assertEqual(len(result.results), 2)
        self.assertIn('results', requests[0]['messages'][0]['content'])
        self.assertTrue(client.is_closed())

    def test_workflow_publishes_ordered_batch_once_and_never_on_cancel_or_invalid_item(self):
        capture = Mock(spec=ScreenCapture)
        target = WindowTarget(123, 456, 0, 0, 100, 100)
        capture.capture.return_value = synthetic_image()
        provider = Mock(spec=BaseLLMProvider)
        provider.supports_vision = True
        provider.analyze_image.return_value = parse_vision_response(json.dumps(batch_payload()))
        workflow = VisionWorkflow(capture, lambda: provider, lambda status: None)
        with self.assertLogs('autoquestion', 'INFO') as logs:
            workflow.for_target(target)(threading.Event())
        results = [r.question_results for r in logs.records if hasattr(r, 'question_results')]
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]), 2)
        capture.capture.assert_called_once_with(target)
        provider.analyze_image.assert_called_once()
        provider.answer_question.assert_not_called()
        stop = threading.Event()
        def cancelled(image):
            stop.set()
            return parse_vision_response(json.dumps(batch_payload()))
        provider.analyze_image.side_effect = cancelled
        with patch.object(logging.getLogger('autoquestion'), 'info') as info:
            workflow.for_target(target)(stop)
        info.assert_not_called()
        provider.analyze_image.side_effect = None
        valid = parse_vision_response(json.dumps(batch_payload()))
        bad_item = valid.results[1].model_copy(update={'answer': valid.results[0].answer})
        provider.analyze_image.return_value = valid.model_copy(update={'results': (valid.results[0], bad_item)})
        with patch.object(logging.getLogger('autoquestion'), 'info') as info:
            with self.assertRaises(LLMProviderError):
                workflow.for_target(target)(threading.Event())
        info.assert_not_called()


if __name__ == '__main__':
    unittest.main()
