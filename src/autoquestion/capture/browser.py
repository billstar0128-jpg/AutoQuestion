"""只读 Browser DOM → 现有 Question；不调用模型，也不操作答案控件。"""

import logging
from pathlib import Path
import re

from playwright.sync_api import Error as PlaywrightError, Page
from playwright.async_api import Page as AsyncPage
from pydantic import ValidationError

from ..schemas import Option, Question, QuestionType, SourceType

LOGGER = logging.getLogger("autoquestion")
EXTRACT_SCRIPT = Path(__file__).with_name("dom_extract.js").read_text(encoding="utf-8")
PREFIX = re.compile(r"^(?:([A-Z])[.．、]\s*|\(([A-Z])\)\s*|([A-Z])\s+)(\S.*)$", re.DOTALL)


class BrowserExtractionError(RuntimeError):
    """固定错误消息，不回显页面、URL 参数或底层浏览器异常。"""


def validated_dom_question(value: Question, *, require_dom: bool = True) -> Question:
    """重新验证模型，拒绝 model_construct/model_copy 绕过字段验证的对象。"""
    try:
        if not isinstance(value, Question):
            raise ValueError
        question = Question.model_validate(value.model_dump(mode="python", warnings=False))
        if (require_dom and question.source_type != SourceType.DOM) or len(question.question_text) > 8000:
            raise ValueError
        if question.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE, QuestionType.TRUE_FALSE):
            if not 2 <= len(question.options) <= 50:
                raise ValueError
        if any(len(option.text) > 2000 for option in question.options):
            raise ValueError
        return question
    except (ValidationError, ValueError, TypeError, AttributeError):
        raise BrowserExtractionError("DOM Question 基本结构无效。") from None


def validated_dom_questions(value, *, require_dom: bool = True) -> tuple[Question, ...]:
    """在调用 Provider 前原子验证整个获取结果，兼容旧单题扩展。"""
    values = (value,) if isinstance(value, Question) else value
    if not isinstance(values, (tuple, list)) or not 1 <= len(values) <= 10:
        raise BrowserExtractionError("DOM 题组结构无效，单次最多读取 10 道完整题目。")
    questions = tuple(validated_dom_question(question, require_dom=require_dom) for question in values)
    identities = [question.model_dump_json() for question in questions]
    if len(identities) != len(set(identities)):
        raise BrowserExtractionError("DOM 题组含有完全重复的题目，无法可靠区分。")
    return questions


def parse_options(texts: list[str]) -> list[Option]:
    """明确标点前缀直接提取；仅空格前缀需整组 A/B/C 顺序佐证。"""
    matches = [PREFIX.fullmatch(text) for text in texts]
    sequential = all(match and next(value for value in match.groups()[:3] if value) == chr(65 + i)
                     for i, match in enumerate(matches))
    options = []
    for index, (text, match) in enumerate(zip(texts, matches)):
        label = None
        if match and (not match.group(3) or sequential):
            label = next(value for value in match.groups()[:3] if value)
            text = match.group(4).strip()
        options.append(Option(index=index, label=label, text=text))
    return options


def question_from_dom(data: dict) -> Question:
    """将小型 DOM 语义快照转换为统一 Schema，不生成第二套题目类型。"""
    if not isinstance(data, dict):
        raise BrowserExtractionError("DOM 题目不符合统一 Question 结构。")
    if data.get("error"):
        messages = {
            "no_question": "页面没有可识别的可见题目。",
            "ambiguous_question": "页面有多个题组，无法确定当前题；请只显示一道题或聚焦题组。",
            "incomplete_question": "题干或选项标签不完整，无法可靠提取。",
        }
        raise BrowserExtractionError(messages.get(data["error"], "页面题目范围过大，无法可靠提取。"))
    try:
        if data["kind"] in ('fill_blank', 'short_answer'):
            if data['options'] != []:
                raise BrowserExtractionError("主观题不能混入选择题选项。")
            fields = dict(question_text=data['question_text'], question_type=data['kind'], source_type=SourceType.DOM, options=[])
            if 'blank_count' in data:
                fields['blank_count'] = data['blank_count']
            return validated_dom_question(Question(**fields))
        options = parse_options(data["options"])
        words = {option.text.casefold() for option in options}
        if data["kind"] == "checkbox":
            kind = QuestionType.MULTIPLE_CHOICE
        elif data["kind"] == "radio":
            kind = QuestionType.SINGLE_CHOICE
            if len(options) == 2 and words in ({"正确", "错误"}, {"对", "错"}, {"是", "否"}, {"true", "false"}, {"yes", "no"}):
                kind = QuestionType.TRUE_FALSE
        else:
            raise BrowserExtractionError("不支持当前题目控件类型。")
        if data.get("hint") and data["hint"] != kind.value:
            raise BrowserExtractionError("页面题型标记与实际控件或选项不一致。")
        question = Question(question_text=data["question_text"], question_type=kind,
                            source_type=SourceType.DOM, options=options)
    except (ValidationError, KeyError, TypeError, AttributeError):
        raise BrowserExtractionError("DOM 题目不符合统一 Question 结构。") from None
    LOGGER.debug("DOM extracted: type=%s options=%d source=DOM", kind.value, len(options))
    return question


def questions_from_dom(data: dict) -> tuple[Question, ...]:
    """原子验证有界题组；任意题不完整时不把剩余选项拼成另一道题。"""
    if not isinstance(data, dict) or data.get("error"):
        question_from_dom(data)  # Reuse fixed, privacy-safe acquisition messages.
        raise BrowserExtractionError("DOM 题组结构无效。")
    values = data.get("questions")
    if set(data) != {"questions"} or not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise BrowserExtractionError("DOM 题组结构无效，单次最多读取 10 道完整题目。")
    return validated_dom_questions(tuple(question_from_dom(value) for value in values))


class BrowserDOMAdapter:
    """Page 必须由调用线程持有。读取当前渲染结果，不获取整页源码。"""

    def __init__(self, page: Page) -> None:
        self.page = page

    def extract_question(self) -> Question:
        return question_from_dom(self._extract(False))

    def extract_questions(self) -> tuple[Question, ...]:
        return questions_from_dom(self._extract(True))

    def _extract(self, all_questions: bool) -> dict:
        try:
            if self.page.is_closed():
                raise BrowserExtractionError("浏览器页面已关闭，请重启 DOM 模式。")
            data = self.page.locator("body").evaluate(EXTRACT_SCRIPT, all_questions, timeout=5000)
        except PlaywrightError:
            raise BrowserExtractionError("无法读取浏览器页面；页面可能已关闭、正在导航或连接已失效。") from None
        return data


class AsyncBrowserDOMAdapter:
    """常驻浏览器使用异步传输；复用相同提取脚本、Schema 和错误语义。"""

    def __init__(self, page: AsyncPage) -> None:
        self.page = page

    async def extract_question(self) -> Question:
        return question_from_dom(await self._extract(False))

    async def extract_questions(self) -> tuple[Question, ...]:
        return questions_from_dom(await self._extract(True))

    async def _extract(self, all_questions: bool) -> dict:
        try:
            if self.page.is_closed():
                raise BrowserExtractionError("浏览器页面已关闭，请重启 DOM 模式。")
            data = await self.page.locator("body").evaluate(EXTRACT_SCRIPT, all_questions, timeout=5000)
        except PlaywrightError:
            raise BrowserExtractionError("无法读取浏览器页面；页面可能已关闭、正在导航或连接已失效。") from None
        return data
