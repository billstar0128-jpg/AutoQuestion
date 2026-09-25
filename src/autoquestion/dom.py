"""显式 DOM 模式；仅在本地提取成功后复用 Text Provider，无 Vision 回退。"""

from collections.abc import Callable
import logging
import threading

from .browser_session import BrowserSession
from .config import Config, load_llm_config
from .llm.fake import FakeLLMProvider
from .schemas import Question, QuestionType, format_answer, validate_answer_against_question

LOGGER = logging.getLogger("autoquestion")


def make_dom_callback(config: Config, browser: BrowserSession,
                      report_status: Callable[[str], None]) -> Callable[[threading.Event], None]:
    def callback(stop: threading.Event) -> None:
        if stop.is_set():
            return
        report_status("EXTRACTING")
        question = browser.extract_question()
        if stop.is_set():
            return
        answer_dom_question(config, question, stop, report_status)
    return callback


def answer_dom_question(config: Config, question: Question, stop: threading.Event,
                        report_status: Callable[[str], None]) -> None:
    """共同的文本回答流程；调用方不得在本函数失败后重新获取图像。"""
    if stop.is_set():
        return
    LOGGER.info("Question:\n%s", question.question_text)
    if question.question_type not in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
        LOGGER.info("已识别题型 %s，%d 个选项；当前尚不支持求解。",
                    question.question_type.value, len(question.options))
        for option in question.options:
            LOGGER.info("[%d] %s", option.index, option.text)
        return
    if config.llm_provider == "fake":
        provider = FakeLLMProvider()
    else:
        from .llm.openai_compatible import OpenAICompatibleProvider
        provider = OpenAICompatibleProvider(config.llm_config or load_llm_config())
    report_status("ANALYZING")
    answer = provider.answer_question(question)
    answer = validate_answer_against_question(question, answer)
    if not stop.is_set():
        LOGGER.info("%s\nConfidence:\n%.0f%%", format_answer(answer), answer.confidence * 100)
