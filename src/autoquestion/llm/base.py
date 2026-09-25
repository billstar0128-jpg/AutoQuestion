"""Provider 只接收 Question 并返回 AnswerResult，不依赖热键或 UI。"""

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING

from ..schemas import AnswerResult, Question, VisionAnalysisResult

if TYPE_CHECKING:
    from ..capture.screen import CapturedImage


class LLMProviderError(RuntimeError):
    """只使用固定、安全的错误消息，不包含 API 响应或凭据。"""


class LLMResponseParseError(LLMProviderError):
    """模型响应无法转换成约定的数据结构。"""


class BaseLLMProvider(ABC):
    supports_vision: bool = False

    @abstractmethod
    def answer_question(self, question: Question) -> AnswerResult:
        """返回通过协议与题目一致性验证的答案。"""

    def analyze_image(self, image: "CapturedImage") -> VisionAnalysisResult:
        """默认明确拒绝，旧的纯文本 Provider 无需实现图像能力。"""
        raise LLMProviderError("Current model is not configured for vision.")
