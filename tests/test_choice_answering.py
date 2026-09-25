"""M10：协议、Text/Vision Mock SDK、DOM/AUTO 工作流；不连接外部 API。"""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import httpx
from openai import OpenAI
from pydantic import ValidationError
from autoquestion.app import TaskRunner, Status
from autoquestion.browser_session import BrowserSession
from autoquestion.capture.screen import ScreenCapture, WindowTarget
from autoquestion.config import Config
from autoquestion.dom import answer_dom_question
from autoquestion.llm.base import LLMProviderError, LLMResponseParseError
from autoquestion.llm.fake import FakeLLMProvider
from autoquestion.llm.openai_compatible import OpenAICompatibleProvider
from autoquestion.llm.parsing import parse_answer_response, parse_vision_response
from autoquestion.router import InputRouter
from autoquestion.schemas import (AnswerResult, AnswerValidationError, Option, Question,
    QuestionType, SourceType, VisionAnalysisResult, format_answer, validate_answer_against_question)
from autoquestion.vision import VisionWorkflow
from test_capture import synthetic_image
from test_llm import config, completion


def choice_question(kind='multiple_choice', labeled=False, source='DOM'):
    texts = ['Python', 'C', 'HTML', 'Java'] if kind == 'multiple_choice' else ['正确', '错误']
    return Question(question_text='以下哪些属于编程语言？' if kind == 'multiple_choice' else '地球绕太阳公转。',
                    question_type=kind, source_type=source,
                    options=[Option(index=i, label=chr(65+i) if labeled else None, text=text)
                             for i, text in enumerate(texts)])


def choice_answer(kind='multiple_choice', labeled=False, indices=(0, 1, 3)):
    data = dict(question_type=kind, confidence=0.98, short_reason='测试答案。')
    if kind == 'multiple_choice':
        data.update(selected_indices=list(indices), selected_labels=[chr(65+i) if labeled else None for i in indices],
                    selected_texts=[['Python', 'C', 'HTML', 'Java'][i] for i in indices])
    else:
        data.update(selected_index=0, selected_label='A' if labeled else None, selected_text='正确')
    return data


class ChoiceSchemaTests(unittest.TestCase):
    def test_multi_labeled_unlabeled_and_roundtrip(self):
        for labeled, display in ((True, '答案：A、B、D'), (False, '答案：Python、C、Java')):
            with self.subTest(labeled=labeled):
                answer = parse_answer_response(json.dumps(choice_answer(labeled=labeled)), choice_question(labeled=labeled))
                self.assertEqual(format_answer(answer), display)
                self.assertEqual(answer.selected_texts, ('Python', 'C', 'Java'))
                self.assertIsNone(answer.selected_text)
                self.assertEqual(AnswerResult.model_validate_json(answer.model_dump_json()), answer)

    def test_out_of_order_is_normalized_after_validation_without_mutating_input(self):
        raw = AnswerResult(**choice_answer(labeled=True, indices=(3, 0, 1)))
        answer = validate_answer_against_question(choice_question(labeled=True), raw)
        self.assertEqual(raw.selected_indices, (3, 0, 1))
        self.assertEqual(answer.selected_indices, (0, 1, 3))
        self.assertEqual(answer.selected_labels, ('A', 'B', 'D'))
        self.assertEqual(answer.selected_texts, ('Python', 'C', 'Java'))

    def test_order_uses_question_positions_not_numeric_indices(self):
        question = choice_question()
        question = question.model_copy(update={'options': tuple(o.model_copy(update={'index': i})
            for o, i in zip(question.options, (30, 10, 80, 20)))})
        data = choice_answer(indices=(3, 0, 1)) | {'selected_indices': [20, 30, 10]}
        answer = parse_answer_response(json.dumps(data), question)
        self.assertEqual(answer.selected_indices, (30, 10, 20))
        self.assertEqual(answer.selected_texts, ('Python', 'C', 'Java'))

    def test_one_selected_option_is_valid_multi(self):
        answer = parse_answer_response(json.dumps(choice_answer(indices=(0,))), choice_question())
        self.assertEqual(answer.selected_indices, (0,))
        self.assertEqual(format_answer(answer), '答案：Python')

    def test_mixed_labels_preserve_each_original_value(self):
        question = choice_question()
        question = question.model_copy(update={'options': (question.options[0].model_copy(update={'label': 'A'}), *question.options[1:])})
        data = choice_answer() | {'selected_labels': ['A', None, None]}
        answer = parse_answer_response(json.dumps(data), question)
        self.assertEqual(format_answer(answer), '答案：A、C、Java')
        self.assertEqual(answer.selected_labels, ('A', None, None))

    def test_multi_empty_duplicate_lengths_and_singular_fields_rejected(self):
        changes = [
            {'selected_indices': [], 'selected_labels': [], 'selected_texts': []},
            {'selected_indices': [0, 0, 3]}, {'selected_indices': [0, True, 3]},
            {'selected_indices': ['0', 1, 3]}, {'selected_indices': [-1, 1, 3]},
            {'selected_labels': [None]}, {'selected_texts': ['Python']},
            {'selected_labels': []}, {'selected_texts': []}, {'selected_labels': None},
            {'selected_texts': ['Python', ' ', 'Java']}, {'selected_labels': ['', None, None]},
            {'selected_index': 0}, {'selected_label': 'A'}, {'selected_text': 'Python'},
        ]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(LLMResponseParseError):
                parse_answer_response(json.dumps(choice_answer() | change), choice_question())

    def test_nonexistent_index_wrong_label_text_and_misalignment_rejected(self):
        for change in ({'selected_indices': [0, 1, 99]}, {'selected_labels': ['A', None, None]},
                       {'selected_texts': ['Python', 'HTML', 'Java']}, {'selected_indices': [3, 0, 1]}):
            with self.subTest(change=change), self.assertRaises(AnswerValidationError):
                parse_answer_response(json.dumps(choice_answer() | change), choice_question())
        with self.assertRaises(AnswerValidationError):
            parse_answer_response(json.dumps(choice_answer()), choice_question(labeled=True))

    def test_unvalidated_provider_objects_cannot_be_silently_truncated_or_deduplicated(self):
        answer = AnswerResult(**choice_answer())
        for changes in ({'selected_indices': ()}, {'selected_labels': ()},
                        {'selected_texts': ('Python',)}, {'selected_indices': (0, 0, 3)}):
            with self.subTest(changes=changes), self.assertRaises(AnswerValidationError):
                validate_answer_against_question(choice_question(), answer.model_copy(update=changes))

    def test_old_single_format_for_multi_and_wrong_question_type_rejected(self):
        old = dict(question_type='multiple_choice', selected_index=0, selected_label=None,
                   selected_text='Python', confidence=0.9, short_reason='旧格式')
        with self.assertRaises(LLMResponseParseError):
            parse_answer_response(json.dumps(old), choice_question())
        old['question_type'] = 'single_choice'
        with self.assertRaises(AnswerValidationError):
            parse_answer_response(json.dumps(old), choice_question())

    def test_true_false_text_and_real_label_preserved(self):
        for labeled, display in ((False, '答案：正确'), (True, '答案：A')):
            answer = parse_answer_response(json.dumps(choice_answer('true_false', labeled)), choice_question('true_false', labeled))
            self.assertEqual(format_answer(answer), display)
            self.assertEqual(answer.selected_text, '正确')
            self.assertEqual(answer.question_type, QuestionType.TRUE_FALSE)
        for texts in (('是', '否'), ('True', 'False')):
            q = Question(question_text='判断', question_type='true_false',
                         options=[Option(index=i, text=t) for i, t in enumerate(texts)])
            answer = parse_answer_response(json.dumps(choice_answer('true_false') | {'selected_text': texts[0]}), q)
            self.assertEqual(format_answer(answer), '答案：' + texts[0])

    def test_true_false_bad_selection_or_multi_fields_rejected(self):
        q = choice_question('true_false')
        for change in ({'selected_index': 9}, {'selected_text': '错误'}, {'selected_label': 'A'}):
            with self.subTest(change=change), self.assertRaises(AnswerValidationError):
                parse_answer_response(json.dumps(choice_answer('true_false') | change), q)
        for change in ({'selected_index': None}, {'selected_text': None}, {'selected_text': True},
                       {'selected_indices': [0]}, {'selected_labels': [None]}, {'selected_texts': ['正确']}):
            with self.subTest(change=change), self.assertRaises(LLMResponseParseError):
                parse_answer_response(json.dumps(choice_answer('true_false') | change), q)

    def test_question_option_counts_and_missing_single_text(self):
        for kind, count in (('multiple_choice', 0), ('multiple_choice', 1), ('true_false', 0), ('true_false', 1), ('true_false', 3)):
            with self.subTest(kind=kind, count=count), self.assertRaises(ValidationError):
                Question(question_text='题目', question_type=kind, options=[Option(index=i, text=str(i)) for i in range(count)])
        with self.assertRaises(ValidationError):
            AnswerResult(question_type='single_choice', selected_index=0, confidence=0.9, short_reason='缺文本')

    def test_fake_strictly_accepts_only_known_demo_questions(self):
        provider = FakeLLMProvider()
        for kind, display in (('multiple_choice', '答案：Python、C、Java'), ('true_false', '答案：正确')):
            q = choice_question(kind)
            self.assertEqual(format_answer(provider.answer_question(q)), display)
            for wrong in (q.model_copy(update={'question_text': '其他题目'}), choice_question(kind, True),
                          choice_question(kind, source='VISION'), q.model_copy(update={'options': tuple(reversed(q.options))})):
                with self.subTest(kind=kind), self.assertRaises(LLMProviderError):
                    provider.answer_question(wrong)


class ChoiceSDKTests(unittest.TestCase):
    def invoke(self, question, answer, vision=False):
        calls = []
        payload = {'question': question.model_dump(mode='json'), 'answer': answer} if vision else answer
        def handler(request):
            body = json.loads(request.content)
            calls.append(body)
            if not vision:
                self.assertEqual(json.loads(body['messages'][1]['content']), question.model_dump(mode='json'))
                self.assertNotIn('image_url', str(body))
            else:
                self.assertEqual(body['messages'][1]['content'][1]['type'], 'image_url')
            self.assertIn('multiple_choice', body['messages'][0]['content'])
            self.assertIn('true_false', body['messages'][0]['content'])
            self.assertIn('selected_labels', body['messages'][0]['content'])
            return httpx.Response(200, json=completion(json.dumps(payload, ensure_ascii=False)))
        client = OpenAI(api_key='test-api-key', base_url='https://example.invalid/v1', max_retries=0,
                        http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.addCleanup(client.close)
        with patch('autoquestion.llm.openai_compatible.OpenAI', return_value=client):
            provider = OpenAICompatibleProvider(replace(config(), supports_vision=vision))
            result = provider.analyze_image(synthetic_image()) if vision else provider.answer_question(question)
        self.assertEqual(len(calls), 1)
        self.assertTrue(client.is_closed())
        return result

    def test_text_sdk_labeled_unlabeled_multi_and_true_false(self):
        for kind in ('multiple_choice', 'true_false'):
            for labeled in (True, False):
                with self.subTest(kind=kind, labeled=labeled):
                    q = choice_question(kind, labeled)
                    result = self.invoke(q, choice_answer(kind, labeled, (3, 0, 1)))
                    self.assertEqual(result.question_type, q.question_type)
                    if kind == 'multiple_choice':
                        self.assertEqual(result.selected_indices, (0, 1, 3))
                    self.assertEqual(format_answer(result), ('答案：A、B、D' if labeled else '答案：Python、C、Java')
                                     if kind == 'multiple_choice' else ('答案：A' if labeled else '答案：正确'))

    def test_vision_sdk_three_types_new_answers_and_canonical_order(self):
        for kind in ('multiple_choice', 'true_false'):
            for labeled in (True, False):
                with self.subTest(kind=kind, labeled=labeled):
                    q = choice_question(kind, labeled, 'VISION')
                    result = self.invoke(q, choice_answer(kind, labeled, (3, 0, 1)), vision=True)
                    self.assertEqual(result.question, q)
                    self.assertEqual(result.question.source_type, SourceType.VISION)
                    self.assertEqual(result.answer, validate_answer_against_question(q, result.answer))
                    self.assertEqual(format_answer(result.answer), ('答案：A、B、D' if labeled else '答案：Python、C、Java')
                                     if kind == 'multiple_choice' else ('答案：A' if labeled else '答案：正确'))
                    if kind == 'multiple_choice':
                        self.assertEqual(result.answer.selected_indices, (0, 1, 3))
                        self.assertEqual(result.answer.selected_texts, ('Python', 'C', 'Java'))

    def test_invalid_vision_answers_are_rejected_with_safe_errors(self):
        for kind, changes in (('multiple_choice', {'selected_indices': []}),
                              ('multiple_choice', {'selected_labels': ['A', None, None]}),
                              ('multiple_choice', {'selected_texts': ['PRIVATE', 'C', 'Java']}),
                              ('true_false', {'selected_index': 9})):
            payload = {'question': choice_question(kind, source='VISION').model_dump(mode='json'),
                       'answer': choice_answer(kind) | changes}
            with self.subTest(kind=kind), self.assertRaises(LLMResponseParseError) as error:
                parse_vision_response(json.dumps(payload))
            self.assertNotIn('PRIVATE', str(error.exception))


class ChoiceWorkflowTests(unittest.TestCase):
    def run_job(self, runner):
        with self.assertLogs('autoquestion', level='INFO') as logs:
            self.assertTrue(runner.trigger())
            runner._worker.join(10)
            self.assertFalse(runner._worker.is_alive())
        self.assertEqual(runner.state, Status.READY)
        return '\n'.join(logs.output)

    def test_real_browser_auto_answers_four_types_without_vision(self):
        browser = BrowserSession(headless=True)
        self.addCleanup(browser.close)
        browser.start()
        capture = Mock(spec=ScreenCapture)
        capture.snapshot_target.return_value = WindowTarget(123, browser._process_id, 0, 0, 900, 700)
        provider = Mock(wraps=FakeLLMProvider())
        vision = Mock(spec=VisionWorkflow)
        report = lambda status: runner.update_status(status)
        router = InputRouter(capture, browser,
            lambda q, stop: answer_dom_question(Config(input_mode='auto'), q, stop, report), vision, report)
        runner = TaskRunner(prepare=router.prepare, prepare_status=Status.ROUTING, clock=lambda: 100+runner.trigger_count)
        self.addCleanup(runner.close)
        with patch('autoquestion.browser_session.WindowsWindowAPI') as api, patch('autoquestion.dom.FakeLLMProvider', return_value=provider):
            api.return_value.browser_windows.return_value = [123]
            for number, expected in enumerate(('答案：A', '答案：木星', '答案：Python、C、Java', '答案：正确')):
                output = self.run_job(runner)
                self.assertIn(expected, output)
                self.assertIn('Input: DOM', output)
                self.assertNotIn('ERROR', output)
                self.assertEqual(output.count('答案：'), 1)
                self.assertEqual(browser._call(lambda: browser._adapter.page.locator('input:checked').count()), 0)
                if number < 3:
                    browser._call(lambda: browser._adapter.page.get_by_role('button', name='下一题').click())
        self.assertEqual(provider.answer_question.call_count, 4)
        capture.capture.assert_not_called()
        vision.for_target.assert_not_called()

    def test_new_type_answer_errors_ready_without_auto_fallback_then_retry(self):
        capture = Mock(spec=ScreenCapture)
        browser, vision, provider = Mock(), Mock(spec=VisionWorkflow), Mock()
        report = lambda status: runner.update_status(status)
        router = InputRouter(capture, browser,
            lambda q, stop: answer_dom_question(Config(input_mode='auto'), q, stop, report), vision, report)
        runner = TaskRunner(prepare=router.prepare, prepare_status=Status.ROUTING, clock=lambda: 100+runner.trigger_count)
        self.addCleanup(runner.close)
        with patch('autoquestion.dom.FakeLLMProvider', return_value=provider):
            for kind, change in (('multiple_choice', {'selected_texts': ['错误', 'C', 'Java']}),
                                 ('multiple_choice', {'selected_indices': []}), ('true_false', {'selected_index': 9})):
                q = choice_question(kind)
                browser.extract_for_target.return_value = q
                invalid = json.dumps(choice_answer(kind) | change)
                provider.answer_question.side_effect = lambda question: parse_answer_response(invalid, question)
                self.assertIn('Status: ERROR', self.run_job(runner))
                provider.answer_question.side_effect = FakeLLMProvider().answer_question
                self.assertNotIn('Status: ERROR', self.run_job(runner))
        self.assertEqual(provider.answer_question.call_count, 6)
        capture.capture.assert_not_called()
        vision.for_target.assert_not_called()

    def test_vision_and_auto_fallback_display_new_types_and_return_ready(self):
        for auto in (False, True):
            for kind, labeled in (('multiple_choice', True), ('multiple_choice', False), ('true_false', False)):
                with self.subTest(auto=auto, kind=kind, labeled=labeled):
                    capture, provider = Mock(spec=ScreenCapture), Mock()
                    capture.capture.return_value = synthetic_image()
                    provider.supports_vision = True
                    provider.analyze_image.return_value = VisionAnalysisResult(
                        question=choice_question(kind, labeled, 'VISION'), answer=AnswerResult(**choice_answer(kind, labeled, (3, 0, 1))))
                    report = lambda status: runner.update_status(status)
                    workflow = VisionWorkflow(capture, lambda: provider, report)
                    router = InputRouter(capture, None, Mock(), workflow, report)
                    runner = TaskRunner(prepare=router.prepare if auto else workflow.prepare,
                                        prepare_status=Status.ROUTING if auto else Status.CAPTURING)
                    try:
                        text = self.run_job(runner)
                        self.assertIn(('答案：A、B、D' if labeled else '答案：Python、C、Java')
                                      if kind == 'multiple_choice' else '答案：正确', text)
                        self.assertEqual(text.count('答案：'), 1)
                        self.assertNotIn('ERROR', text)
                        capture.capture.assert_called_once()
                        provider.analyze_image.assert_called_once()
                        provider.answer_question.assert_not_called()
                    finally:
                        runner.close()
