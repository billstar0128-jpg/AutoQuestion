"""仅连接固定 MANUAL 题目、Provider 和控制台；没有屏幕输入。"""

from collections.abc import Callable
import logging
import threading

from .config import Config, load_llm_config
from .llm.fake import FakeLLMProvider, demo_question
from .schemas import format_answer, validate_answer_against_question

LOGGER = logging.getLogger("autoquestion")


def make_demo_callback(config: Config) -> Callable[[threading.Event], None]:
    def callback(stop: threading.Event) -> None:
        if stop.wait(0.15):
            return
        question = demo_question()
        if config.llm_provider == "fake":
            provider = FakeLLMProvider()
        else:
            from .llm.openai_compatible import OpenAICompatibleProvider
            provider = OpenAICompatibleProvider(config.llm_config or load_llm_config())
        answer = provider.answer_question(question)
        validate_answer_against_question(question, answer)
        if not stop.is_set():
            LOGGER.info("Question:\n%s\n%s\nConfidence:\n%.0f%%",
                        question.question_text, format_answer(answer), answer.confidence * 100)
    return callback
