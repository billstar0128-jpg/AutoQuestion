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
        options = parse_options(data["options"])
        words = {option.text.casefold() for option in options}
        if data["kind"] == "checkbox":
            kind = QuestionType.MULTIPLE_CHOICE
        elif data["kind"] == "radio":
            kind = QuestionType.SINGLE_CHOICE
            if len(options) == 2 and words in ({"正确", "错误"}, {"对", "错"}, {"是", "否"}, {"true", "false"}):
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


class BrowserDOMAdapter:
    """Page 必须由调用线程持有。读取当前渲染结果，不获取整页源码。"""

    def __init__(self, page: Page) -> None:
        self.page = page

    def extract_question(self) -> Question:
        try:
            if self.page.is_closed():
                raise BrowserExtractionError("浏览器页面已关闭，请重启 DOM 模式。")
            data = self.page.locator("body").evaluate(EXTRACT_SCRIPT, timeout=5000)
        except PlaywrightError:
            raise BrowserExtractionError("无法读取浏览器页面；页面可能已关闭、正在导航或连接已失效。") from None
        return question_from_dom(data)


class AsyncBrowserDOMAdapter:
    """常驻浏览器使用异步传输；复用相同提取脚本、Schema 和错误语义。"""

    def __init__(self, page: AsyncPage) -> None:
        self.page = page

    async def extract_question(self) -> Question:
        try:
            if self.page.is_closed():
                raise BrowserExtractionError("浏览器页面已关闭，请重启 DOM 模式。")
            data = await self.page.locator("body").evaluate(EXTRACT_SCRIPT, timeout=5000)
        except PlaywrightError:
            raise BrowserExtractionError("无法读取浏览器页面；页面可能已关闭、正在导航或连接已失效。") from None
        return question_from_dom(data)
