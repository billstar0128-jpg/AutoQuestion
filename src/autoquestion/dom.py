"""显式 DOM 模式；仅在本地提取成功后复用 Text Provider，无 Vision 回退。"""

from collections.abc import Callable
import logging
import threading

from .browser_session import BrowserSession
from .capture.browser import validated_dom_questions
from .config import Config, load_llm_config
from .llm.fake import FakeLLMProvider
from .schemas import Question, format_answer, validate_answer_against_question

LOGGER = logging.getLogger("autoquestion")


def make_dom_callback(config: Config, browser: BrowserSession,
                      report_status: Callable[[str], None]) -> Callable[[threading.Event], None]:
    def callback(stop: threading.Event) -> None:
        if stop.is_set():
            return
        report_status("EXTRACTING")
        question = browser.extract_question(all_questions=True)
        if stop.is_set():
            return
        answer_dom_question(config, question, stop, report_status)
    return callback


def answer_dom_question(config: Config, question: Question | tuple[Question, ...], stop: threading.Event,
                        report_status: Callable[[str], None]) -> None:
    """共同的文本回答流程；调用方不得在本函数失败后重新获取图像。"""
    if stop.is_set():
        return
    # Acquisition enforces DOM origin; this reusable text-answer entry point also
    # retains its historical MANUAL Question support.
    questions = validated_dom_questions(question, require_dom=False)
    if config.llm_provider == "fake":
        provider = FakeLLMProvider()
    else:
        from .llm.openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(config.llm_config or load_llm_config())
    report_status("ANALYZING")
    results = []
    for current in questions:
        if stop.is_set():
            return
        LOGGER.info("Question:\n%s", current.question_text)
        answer = validate_answer_against_question(current, provider.answer_question(current))
        results.append({'question': current.model_dump(mode='json'), 'answer': answer.model_dump(mode='json')})
    if stop.is_set():
        return
    if len(results) == 1:
        LOGGER.info("%s\nConfidence:\n%.0f%%", format_answer(answer), answer.confidence * 100,
                    extra={'question_result': results[0]['question'], 'answer_result': results[0]['answer']})
    else:
        # Answers are already strictly matched above; construct the public batch once.
        from .schemas import AnswerResult
        text = '\n\n'.join(f"第 {index} 题：{result['question']['question_text']}\n"
                           f"{format_answer(AnswerResult.model_validate(result['answer']))}\n"
                           f"Confidence:\n{result['answer']['confidence'] * 100:.0f}%"
                           for index, result in enumerate(results, 1))
        LOGGER.info("%s", text, extra={'question_results': results})
