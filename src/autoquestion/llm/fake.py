"""离线演示：仅识别内置示例题，不将固定答案伪装为通用推理能力。"""

from ..schemas import AnswerResult, Option, Question, QuestionType, SourceType, validate_answer_against_question
from .base import BaseLLMProvider, LLMProviderError


def demo_question() -> Question:
    return Question(
        question_text="法国的首都是哪里？", question_type="single_choice", source_type="MANUAL",
        options=[Option(index=i, label=label, text=text) for i, (label, text) in enumerate(
            [("A", "巴黎"), ("B", "伦敦"), ("C", "柏林"), ("D", "罗马")]
        )],
    )


class FakeLLMProvider(BaseLLMProvider):
    def answer_question(self, question: Question) -> AnswerResult:
        dom_capital = demo_question().model_copy(update={"source_type": SourceType.DOM})
        dom_planet = Question(
            question_text="太阳系中最大的行星是？", question_type="single_choice", source_type="DOM",
            options=[Option(index=i, text=text) for i, text in enumerate(["木星", "地球", "火星", "金星"])],
        )
        dom_languages = Question(
            question_text="以下哪些属于编程语言？", question_type="multiple_choice", source_type="DOM",
            options=[Option(index=i, text=text) for i, text in enumerate(["Python", "C", "HTML", "Java"])],
        )
        dom_orbit = Question(
            question_text="地球绕太阳公转。", question_type="true_false", source_type="DOM",
            options=[Option(index=i, text=text) for i, text in enumerate(["正确", "错误"])],
        )
        if question not in (demo_question(), dom_capital, dom_planet, dom_languages, dom_orbit):
            raise LLMProviderError("Fake Provider 仅支持内置四道 DOM 演示题及原 MANUAL 首都题。")
        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            chosen = [question.options[i] for i in (0, 1, 3)]
            return validate_answer_against_question(question, AnswerResult(
                question_type=question.question_type,
                selected_indices=tuple(option.index for option in chosen),
                selected_labels=tuple(option.label for option in chosen),
                selected_texts=tuple(option.text for option in chosen),
                confidence=0.99, short_reason="离线预置演示答案：Python、C 和 Java 是编程语言。",
            ))
        option = question.options[0]
        answer = AnswerResult(
            question_type=question.question_type, selected_index=option.index, selected_label=option.label,
            selected_text=option.text, confidence=0.99, short_reason="离线预置演示答案，不代表模型推理。",
        )
        return validate_answer_against_question(question, answer)
