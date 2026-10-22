"""仅在获取输入失败时回退；回答流程明确位于 fallback 异常边界之外。"""
from collections.abc import Callable
import logging
import threading
import time

from .browser_session import BrowserSession
from .browser_identity import BrowserClassifier
from .capture.browser import BrowserExtractionError, validated_dom_question, validated_dom_questions
from .capture.screen import ScreenCapture
from .config import Config
from .dom import answer_dom_question
from .vision import VisionWorkflow, vision_provider

LOGGER = logging.getLogger("autoquestion")


class InputRouter:
    def __init__(self, capture: ScreenCapture, browser: BrowserSession | None,
                 answer_dom: Callable, vision: VisionWorkflow, report_status: Callable[[str], None],
                 *, bridge=None, strict_dom=False):
        self.capture, self.browser = capture, browser
        self.answer_dom, self.vision, self.report_status = answer_dom, vision, report_status
        self.bridge, self.strict_dom = bridge, strict_dom

    def prepare(self) -> Callable[[threading.Event], None]:
        # TaskRunner 在输出日志前调用；仅记录身份、标题和物理边界，不产生图片。
        target = self.capture.snapshot_target()
        managed = self.browser is not None and self.browser.owns_target(target)
        supported = not managed and BrowserClassifier.classify(target.executable) is not None
        pin = self.bridge.pin(target) if supported and not managed and self.bridge is not None else None
        def callback(stop: threading.Event) -> None:
            if stop.is_set():
                return
            started = time.monotonic()
            self.report_status("ROUTING")
            if not managed and not supported:
                if self.strict_dom:
                    raise BrowserExtractionError('DOM 模式需要受管理 Demo 或已连接扩展的 Chrome / Edge 前台页面。')
                LOGGER.info('Input: VISION (desktop target)')
                self.report_status('CAPTURING')
                self.vision.for_target(target)(stop)
                return
            try:
                if managed:
                    value = self.browser.extract_for_target(target, lambda: self.capture.verify_target(target), all_questions=True)
                elif self.bridge is not None:
                    value = self.bridge.extract_for_target(target, lambda: self.capture.verify_target(target), pin, all_questions=True)
                else:
                    raise BrowserExtractionError('Browser DOM unavailable: bridge not connected.')
                questions = validated_dom_questions(value)
            except BrowserExtractionError:
                # 严格限制为 acquisition 错误。CaptureError（目标变化）直接终止。
                if stop.is_set():
                    return
                if self.strict_dom:
                    raise
                if pin is not None:
                    self.capture.target_guard = lambda: self.bridge.verify_pin(pin)
                self.capture.verify_target(target)
                LOGGER.info("Input: %s unavailable\nFallback: VISION\nInput: VISION", 'DOM' if managed else 'Browser DOM')
                LOGGER.debug("Route=VISION acquisition_ms=%.1f", (time.monotonic() - started) * 1000)
                self.report_status("CAPTURING")
                self.vision.for_target(target)(stop)
                return
            if stop.is_set():
                return
            self.capture.verify_target(target)
            LOGGER.info("Input: %s", 'DOM' if managed else 'Browser DOM')
            LOGGER.debug("Route=DOM acquisition_ms=%.1f", (time.monotonic() - started) * 1000)
            # 不在上述 try 内：Provider / JSON / Answer 校验错误绝不能触发 Vision。
            self.answer_dom(questions[0] if len(questions) == 1 else questions, stop)
        return callback


def make_auto_prepare(config: Config, browser: BrowserSession | None, report_status: Callable[[str], None], *, bridge=None):
    def prepare():
        capture = ScreenCapture(config.image_max_edge)
        vision = VisionWorkflow(capture, lambda: vision_provider(config), report_status)
        return InputRouter(capture, browser,
                           lambda question, stop: answer_dom_question(config, question, stop, report_status),
                           vision, report_status, bridge=bridge, strict_dom=config.input_mode == 'dom').prepare()
    return prepare
