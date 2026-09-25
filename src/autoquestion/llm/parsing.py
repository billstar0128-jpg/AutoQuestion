"""有限度容错：只接受唯一的顶层 JSON 对象，不修复或猜测答案。"""

import json
import re

from pydantic import ValidationError

from ..schemas import AnswerResult, Question, VisionAnalysisResult, validate_answer_against_question
from .base import LLMResponseParseError


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-standard JSON number")


def _parse_object(content: str) -> dict[str, object]:
    """所有失败只提供固定提示，不回显原始模型输出或 Pydantic 输入。"""
    if not isinstance(content, str) or not content.strip() or len(content) > 32_000:
        raise LLMResponseParseError("模型响应为空、不是文本或超过长度限制。")
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise LLMResponseParseError("模型未返回可解析的 JSON 对象。")
    prefix, suffix = text[:start], text[end + 1:]
    # 只允许短说明文字；数组、多个围栏或长段内容不能当作可靠答案。
    if len(prefix) + len(suffix) > 200 or any(c in prefix + suffix for c in '[]{}"`'):
        raise LLMResponseParseError("模型响应包含不明确的 JSON 包装或额外内容。")
    try:
        payload = json.loads(text[start:end + 1], object_pairs_hook=_unique_object,
                             parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        raise LLMResponseParseError("模型 JSON 无效或包含多个答案对象。") from None
    return payload


def parse_answer_response(content: str, question: Question) -> AnswerResult:
    payload = _parse_object(content)
    try:
        answer = AnswerResult.model_validate(payload)
    except ValidationError:
        raise LLMResponseParseError("模型 JSON 不符合 AnswerResult 字段约束。") from None
    return validate_answer_against_question(question, answer)


def parse_vision_response(content: str) -> VisionAnalysisResult:
    payload = _parse_object(content)
    if payload == {"error": "unable_to_identify_question"}:
        raise LLMResponseParseError("无法可靠识别唯一、完整的单选、多选或判断题，请调整题目窗口后重试。")
    try:
        return VisionAnalysisResult.model_validate(payload)
    except ValidationError:
        raise LLMResponseParseError("Vision 结果结构无效，或题目与答案不一致。") from None
