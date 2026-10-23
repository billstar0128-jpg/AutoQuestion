"""完整主观答案、按空匹配、原混合题组、Text/Vision Mock SDK 的离线契约。"""
import copy
from dataclasses import replace
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from pydantic import ValidationError
from autoquestion.schemas import AnswerResult, AnswerValidationError, Question, VisionBatchResult, format_answer, validate_answer_against_question
from autoquestion.llm.base import LLMResponseParseError
from autoquestion.llm.parsing import parse_answer_response, parse_vision_response
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from test_capture import synthetic_image
from test_llm import completion, config
from test_vision_batch import mixed_batch_payload

SOLUTION = '解：\n2x = 7 − 3 = 4。\nx = 2。\n检验：2×2+3=7。'


def subjective_payload(kind='short_answer', source='VISION'):
    fill = kind == 'fill_blank'
    return dict(question=dict(question_text='4. 中国首都是___，1+1=___。' if fill else '5. 解方程 2x+3=7，写出步骤。',
                              question_type=kind, source_type=source, options=[], blank_count=2 if fill else None),
                answer=dict(question_type=kind, confidence=0.9, short_reason='按题意给出完整参考答案。',
                            **({'blank_answers': ['北京', '2']} if fill else {'answer_text': SOLUTION})))


def subjective_mixed_payload():
    items = mixed_batch_payload(3)['results']
    items.extend([subjective_payload('fill_blank'), subjective_payload()])
    short = subjective_payload()
    short['question']['question_text'] = '6. 简述节约用水的两个方法。'
    short['answer']['answer_text'] = '1. 及时关闭水龙头。\n2. 收集可利用的水浇花。'
    items.append(short)
    return {'results': items}


class SubjectiveTests(unittest.TestCase):
    def test_fill_order_and_multiline_solution_round_trip(self):
        for kind in ('fill_blank', 'short_answer'):
            data = subjective_payload(kind)
            question = Question.model_validate(data['question'])
            answer = parse_answer_response(json.dumps(data['answer']), question)
            self.assertEqual(AnswerResult.model_validate_json(answer.model_dump_json()), answer)
            self.assertIn('第 1 空：北京\n第 2 空：2' if kind == 'fill_blank' else SOLUTION, format_answer(answer))

    def test_subjective_question_requires_correct_blank_count_and_no_fake_options(self):
        variants = []
        for count in (None, 0, -1, 21, True, '2'):
            variants.append(subjective_payload('fill_blank')['question'] | {'blank_count': count})
        variants.append(subjective_payload()['question'] | {'blank_count': 1})
        variants.append(subjective_payload()['question'] | {'options': [dict(index=0, text='伪选项')]})
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ValidationError):
                Question.model_validate(data)

    def test_wrong_blank_count_cannot_be_accepted_or_silently_truncated(self):
        data = subjective_payload('fill_blank')
        question = Question.model_validate(data['question'])
        for answers in (['北京'], ['北京', '2', '其他']):
            with self.subTest(answers=answers), self.assertRaises(AnswerValidationError):
                parse_answer_response(json.dumps(data['answer'] | {'blank_answers': answers}), question)
        forged = question.model_copy(update={'blank_count': True})
        with self.assertRaises(AnswerValidationError):
            validate_answer_against_question(forged, AnswerResult.model_validate(data['answer']))

    def test_empty_oversized_mixed_fields_and_choice_subjective_field_rejected(self):
        for kind, changes in (
                ('short_answer', {'answer_text': ''}), ('short_answer', {'answer_text': 'x'*12001}),
                ('short_answer', {'blank_answers': ['x']}), ('short_answer', {'selected_index': 0}),
                ('fill_blank', {'blank_answers': []}), ('fill_blank', {'blank_answers': [' ', '2']}),
                ('fill_blank', {'blank_answers': ['x'*2001, '2']}), ('fill_blank', {'answer_text': '北京、2'}),
                ('fill_blank', {'selected_text': '北京'})):
            data = subjective_payload(kind)
            with self.subTest(kind=kind, changes=changes), self.assertRaises(LLMResponseParseError):
                parse_answer_response(json.dumps(data['answer'] | changes), Question.model_validate(data['question']))
        data = mixed_batch_payload(3)['results'][0]
        with self.assertRaises(LLMResponseParseError):
            parse_answer_response(json.dumps(data['answer'] | {'answer_text': '混入主观答案'}), Question.model_validate(data['question']))

    def test_mixed_six_all_five_types_validate_atomically(self):
        payload = subjective_mixed_payload()
        result = parse_vision_response(json.dumps(payload))
        self.assertIsInstance(result, VisionBatchResult)
        self.assertEqual(len(result.results), 6)
        self.assertEqual(result.results[3].answer.blank_answers, ('北京', '2'))
        self.assertEqual(result.results[4].answer.answer_text, SOLUTION)
        payload['results'][3]['answer']['blank_answers'] = ['北京']
        with self.assertRaises(LLMResponseParseError):
            parse_vision_response(json.dumps(payload))

    def test_real_sdk_mock_text_subjective_and_single_image_mixed_batch(self):
        for image in (False, True):
            requests = []
            payload = subjective_mixed_payload() if image else subjective_payload()['answer']
            def handler(request):
                requests.append(json.loads(request.content))
                return httpx.Response(200, json=completion(json.dumps(payload)))
            client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                            http_client=httpx.Client(transport=httpx.MockTransport(handler)))
            with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client):
                provider = OpenAICompatibleProvider(replace(config(), supports_vision=True))
                result = provider.analyze_image(synthetic_image()) if image else provider.answer_question(
                    Question.model_validate(subjective_payload()['question']))
            self.assertEqual(len(requests), 1)
            self.assertTrue(client.is_closed())
            self.assertEqual(result.results[4].answer.answer_text if image else result.answer_text, SOLUTION)
            self.assertIn('blank_answers', requests[0]['messages'][0]['content'])


if __name__ == '__main__':
    unittest.main()
