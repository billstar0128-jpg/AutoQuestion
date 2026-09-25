from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pydantic import ValidationError
from autoquestion.schemas import (
    AnswerResult, AnswerValidationError, Option, Question, QuestionType,
    format_answer, validate_answer_against_question,
)


def sample_question(label="A"):
    return Question(question_text="法国的首都是哪里？", question_type="single_choice",
                    options=[Option(index=10, label=label, text="巴黎"),
                             Option(index=20, label=None, text="伦敦")])


def answer_data(**changes):
    return dict(question_type="single_choice", selected_index=10, selected_label="A",
                selected_text="巴黎", confidence=0.99, short_reason="巴黎是法国首都。") | changes


class SchemaTests(unittest.TestCase):
    def test_labeled_single_choice_and_json_roundtrip(self):
        question = sample_question()
        self.assertEqual(Question.model_validate_json(question.model_dump_json()), question)
        answer = validate_answer_against_question(question, AnswerResult(**answer_data()))
        self.assertEqual(format_answer(answer), "答案：A")
        self.assertEqual(answer.selected_index, 10)
        self.assertEqual(answer.selected_text, "巴黎")

    def test_no_label_is_preserved(self):
        answer = AnswerResult(**answer_data(selected_label=None))
        validate_answer_against_question(sample_question(None), answer)
        self.assertEqual(format_answer(answer), "答案：巴黎")

    def test_invalid_option_values(self):
        for changes in ({"index": -1}, {"index": True}, {"index": "0"},
                        {"text": ""}, {"text": "  "}, {"label": " "}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                Option(**(dict(index=0, text="巴黎") | changes))

    def test_invalid_question_options(self):
        a = Option(index=0, label="A", text="巴黎")
        for options in ([], [a], [a, a], [a, Option(index=1, label="A", text="伦敦")]):
            with self.subTest(options=options), self.assertRaises(ValidationError):
                Question(question_text="首都？", question_type="single_choice", options=options)

    def test_invalid_answer_fields(self):
        for changes in ({"confidence": 1.1}, {"confidence": -0.1}, {"confidence": float("nan")},
                        {"confidence": float("inf")}, {"confidence": True}, {"confidence": "0.9"},
                        {"selected_index": -1}, {"selected_index": None}, {"selected_index": True},
                        {"selected_text": " "}, {"short_reason": "x" * 201},
                        {"selected_indices": [10, 20]}, {"unknown": 1}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                AnswerResult(**answer_data(**changes))

    def test_consistency_rejects_nonexistent_index_wrong_label_text_and_type(self):
        for changes in ({"selected_index": 7}, {"selected_label": "B"},
                        {"selected_label": None}, {"selected_text": "伦敦"},
                        {"question_type": "true_false"}):
            with self.subTest(changes=changes), self.assertRaises(AnswerValidationError):
                validate_answer_against_question(sample_question(), AnswerResult(**answer_data(**changes)))
        with self.assertRaises(AnswerValidationError):
            validate_answer_against_question(sample_question(None), AnswerResult(**answer_data()))

    def test_other_types_are_expressible_but_not_solved(self):
        for kind in (QuestionType.FILL_BLANK, QuestionType.SHORT_ANSWER):
            question = Question(question_text="示例", question_type=kind)
            answer = AnswerResult(question_type=kind, selected_text="示例答案", confidence=0.5,
                                  short_reason="仅测试结构。")
            with self.assertRaises(AnswerValidationError):
                validate_answer_against_question(question, answer)


if __name__ == "__main__":
    unittest.main()
