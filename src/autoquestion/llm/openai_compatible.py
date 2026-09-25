"""官方 SDK 的薄封装；共用文本与图片 Chat Completions 请求。"""

import base64
import logging
from typing import TYPE_CHECKING
import time

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, OpenAI

from ..config import LLMConfig
from ..schemas import AnswerResult, Question, QuestionType, VisionAnalysisResult

if TYPE_CHECKING:
    from ..capture.screen import CapturedImage
from .base import BaseLLMProvider, LLMProviderError, LLMResponseParseError
from .parsing import parse_answer_response, parse_vision_response
from .prompts import SYSTEM_PROMPT, VISION_PROMPT

LOGGER = logging.getLogger("autoquestion")


def _silence_transport_logs() -> None:
    """SDK 调试日志可能含请求内容；只允许本项目的固定诊断信息。"""
    for name in ("openai", "httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL + 1)


class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self.supports_vision = config.supports_vision

    def answer_question(self, question: Question) -> AnswerResult:
        if question.question_type not in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
            raise LLMProviderError("本轮 Provider 仅支持 single_choice、multiple_choice 和 true_false。")
        content = self._request([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question.model_dump_json()},
        ])
        answer = parse_answer_response(content, question)
        LOGGER.debug("Answer schema and consistency validation passed")
        return answer

    def analyze_image(self, image: "CapturedImage") -> VisionAnalysisResult:
        """一张图一次请求：同时识题和答题，不进行第二次文本请求。"""
        if not self.supports_vision:
            raise LLMProviderError("Current model is not configured for vision.")
        encoded = base64.b64encode(image.data).decode("ascii")
        content = self._request([
            {"role": "system", "content": VISION_PROMPT},
            {"role": "user", "content": [
                {"type": "text", "text": "识别并回答当前主要的一道完整单选、多选或判断题。"},
                {"type": "image_url", "image_url": {
                    "url": f"data:{image.media_type};base64,{encoded}"}},
            ]},
        ])
        result = parse_vision_response(content)
        LOGGER.debug("Vision schema and consistency validation passed")
        return result

    def _request(self, messages: list[dict]) -> str:
        """共享 SDK 生命周期、超时和安全异常转换，不记录请求体。"""
        _silence_transport_logs()
        start = time.monotonic()
        try:
            # 每次任务关闭连接资源。显式配置 URL，避免隐式选择服务商。
            with OpenAI(
                api_key=self._config.api_key.get_secret_value(),
                base_url=self._config.base_url,
                timeout=self._config.timeout_seconds,
                max_retries=0,
            ) as client:
                response = client.chat.completions.create(
                    model=self._config.model,
                    messages=messages,
                )
        except APITimeoutError:
            raise LLMProviderError("LLM API 请求超时，请稍后重试。") from None
        except APIConnectionError:
            raise LLMProviderError("无法连接 LLM API，请检查网络和服务地址。") from None
        except APIStatusError as exc:
            if exc.status_code in {401, 403}:
                message = "LLM API 认证或权限失败，请检查本地密钥配置。"
            elif exc.status_code == 429:
                message = "LLM API 请求受限，请检查额度或稍后重试。"
            else:
                message = "LLM API 返回错误状态，请检查模型与服务配置。"
            raise LLMProviderError(message) from None
        except APIError:
            raise LLMProviderError("LLM API 请求失败。") from None
        except Exception:
            raise LLMProviderError("LLM 客户端初始化或请求失败，请检查配置。") from None
        finally:
            LOGGER.debug("LLM request latency: %.3fs", time.monotonic() - start)
        try:
            if not response.choices:
                raise LLMResponseParseError("LLM API 未返回答案选项。")
            choice = response.choices[0]
            if choice.finish_reason != "stop" or choice.message.refusal:
                raise LLMResponseParseError("模型拒绝回答或响应未完整结束。")
            content = choice.message.content
        except (AttributeError, IndexError, TypeError):
            raise LLMResponseParseError("LLM API 响应结构不符合 Chat Completions 协议。") from None
        return content
