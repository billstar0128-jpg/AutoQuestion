"""仅在获取输入失败时回退；回答流程明确位于 fallback 异常边界之外。"""
from collections.abc import Callable
import logging
import threading
import time

from pydantic import ValidationError

from .browser_session import BrowserSession
from .capture.browser import BrowserExtractionError
from .capture.screen import ScreenCapture
from .config import Config
from .dom import answer_dom_question
from .schemas import Question, QuestionType, SourceType
from .vision import VisionWorkflow, vision_provider

LOGGER = logging.getLogger("autoquestion")


def validated_dom_question(value: Question) -> Question:
    """重新验证模型，拒绝 model_construct/model_copy 绕过字段验证的对象。"""
    try:
        if not isinstance(value, Question):
            raise ValueError
        question = Question.model_validate(value.model_dump(mode="python", warnings=False))
        if question.source_type != SourceType.DOM or len(question.question_text) > 8000:
            raise ValueError
        if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
            if not 2 <= len(question.options) <= 50:
                raise ValueError
        if any(len(option.text) > 2000 for option in question.options):
            raise ValueError
        return question
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise BrowserExtractionError("DOM Question 基本结构无效。") from None


class InputRouter:
    def __init__(self, capture: ScreenCapture, browser: BrowserSession | None,
                 answer_dom: Callable, vision: VisionWorkflow, report_status: Callable[[str], None]):
        self.capture, self.browser = capture, browser
        self.answer_dom, self.vision, self.report_status = answer_dom, vision, report_status

    def prepare(self) -> Callable[[threading.Event], None]:
        # TaskRunner 在输出日志前调用；仅记录身份、标题和物理边界，不产生图片。
        target = self.capture.snapshot_target()
        def callback(stop: threading.Event) -> None:
            if stop.is_set():
                return
            started = time.monotonic()
            self.report_status("ROUTING")
            try:
                if self.browser is None:
                    raise BrowserExtractionError("没有可用受管理页面。")
                question = validated_dom_question(self.browser.extract_for_target(
                    target, lambda: self.capture.verify_target(target)))
            except BrowserExtractionError:
                # 严格限制为 acquisition 错误。CaptureError（目标变化）直接终止。
                if stop.is_set():
                    return
                LOGGER.info("Input: DOM unavailable\nFallback: VISION\nInput: VISION")
                LOGGER.debug("Route=VISION acquisition_ms=%.1f", (time.monotonic() - started) * 1000)
                self.report_status("CAPTURING")
                self.vision.for_target(target)(stop)
                return
            if stop.is_set():
                return
            self.capture.verify_target(target)
            LOGGER.info("Input: DOM")
            LOGGER.debug("Route=DOM acquisition_ms=%.1f", (time.monotonic() - started) * 1000)
            # 不在上述 try 内：Provider / JSON / Answer 校验错误绝不能触发 Vision。
            self.answer_dom(question, stop)
        return callback


def make_auto_prepare(config: Config, browser: BrowserSession | None, report_status: Callable[[str], None]):
    def prepare():
        capture = ScreenCapture(config.image_max_edge)
        vision = VisionWorkflow(capture, lambda: vision_provider(config), report_status)
        return InputRouter(capture, browser,
                           lambda question, stop: answer_dom_question(config, question, stop, report_status),
                           vision, report_status).prepare()
    return prepare
