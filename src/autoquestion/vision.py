"""F8 的 Vision 流程；窗口快照同步准备，捕获与 API 在现有工作线程执行。"""

from collections.abc import Callable
import logging
import threading

from .capture.screen import ScreenCapture, WindowTarget
from .config import Config, load_llm_config
from .llm.base import BaseLLMProvider, LLMProviderError
from .llm.openai_compatible import OpenAICompatibleProvider
from .schemas import format_answer, validate_answer_against_question

LOGGER = logging.getLogger("autoquestion")


class VisionWorkflow:
    def __init__(self, capture: ScreenCapture, provider_factory: Callable[[], BaseLLMProvider],
                 report_status: Callable[[str], None]) -> None:
        self.capture = capture
        self.provider_factory = provider_factory
        self.report_status = report_status

    def prepare(self) -> Callable[[threading.Event], None]:
        """仅记录目标，不截屏、不联网、不输出日志。"""
        target = self.capture.snapshot_target()
        return self.for_target(target)

    def for_target(self, target: WindowTarget) -> Callable[[threading.Event], None]:
        """复用 F8 的目标；AUTO fallback 不重新获取前台窗口。"""

        def callback(stop: threading.Event) -> None:
            if stop.is_set():
                return
            provider = self.provider_factory()
            if not provider.supports_vision:
                raise LLMProviderError("Current model is not configured for vision.")
            image = self.capture.capture(target)
            if stop.is_set():
                return
            self.report_status("ANALYZING")
            result = provider.analyze_image(image)
            answer = validate_answer_against_question(result.question, result.answer)
            if not stop.is_set():
                LOGGER.info("Question:\n%s\n%s\nConfidence:\n%.0f%%", result.question.question_text,
                            format_answer(answer), answer.confidence * 100)
        return callback


def make_vision_prepare(config: Config, report_status: Callable[[str], None]
                        ) -> Callable[[], Callable[[threading.Event], None]]:
    # 延迟初始化 Windows API，失败可由 TaskRunner 恢复 READY，而非阻止启动。
    def prepare() -> Callable[[threading.Event], None]:
        capture = ScreenCapture(config.image_max_edge)
        return VisionWorkflow(capture, lambda: vision_provider(config), report_status).prepare()
    return prepare


def vision_provider(config: Config) -> BaseLLMProvider:
    if config.llm_provider != "openai":
        raise LLMProviderError("Vision 需要 LLM_PROVIDER=openai 且启用图像能力；当前配置不会截图或请求。")
    return OpenAICompatibleProvider(config.llm_config or load_llm_config())
