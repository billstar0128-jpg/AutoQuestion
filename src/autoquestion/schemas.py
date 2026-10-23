"""统一数据协议；字段校验与题目/答案之间的业务校验分别维护。"""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

NonEmptyText = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
Index = Annotated[int, Field(strict=True, ge=0)]


class QuestionType(str, Enum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    SHORT_ANSWER = "short_answer"


class SourceType(str, Enum):
    DOM = "DOM"
    VISION = "VISION"
    MANUAL = "MANUAL"


class SchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class Option(SchemaModel):
    index: Index
    label: NonEmptyText | None = None
    text: NonEmptyText


class Question(SchemaModel):
    question_text: NonEmptyText
    question_type: QuestionType
    options: tuple[Option, ...] = ()
    source_type: SourceType = SourceType.MANUAL
    blank_count: Annotated[int, Field(strict=True, ge=1, le=20)] | None = None

    @model_validator(mode="after")
    def validate_options(self) -> "Question":
        if self.question_type in (QuestionType.FILL_BLANK, QuestionType.SHORT_ANSWER):
            if self.options:
                raise ValueError("填空、简答和解答题不使用选项。")
            if self.question_type == QuestionType.FILL_BLANK and self.blank_count is None:
                raise ValueError("填空题必须明确空的数量。")
        if self.question_type != QuestionType.FILL_BLANK and self.blank_count is not None:
            raise ValueError("仅填空题可以指定 blank_count。")
        if self.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE) and len(self.options) < 2:
            raise ValueError("单选/多选题至少需要两个选项。")
        if self.question_type == QuestionType.TRUE_FALSE and len(self.options) != 2:
            raise ValueError("判断题必须有两个选项。")
        indices = [option.index for option in self.options]
        if len(indices) != len(set(indices)):
            raise ValueError("选项 index 不能重复。")
        labels = [option.label for option in self.options if option.label is not None]
        if len(labels) != len(set(labels)):
            raise ValueError("非空选项 label 不能重复。")
        return self


class AnswerResult(SchemaModel):
    question_type: QuestionType
    selected_index: Index | None = None
    selected_label: NonEmptyText | None = None
    # 多选不使用单值字段；旧单选 JSON 的必填语义由下方题型校验保留。
    selected_text: NonEmptyText | None = None
    confidence: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
    short_reason: Annotated[NonEmptyText, Field(max_length=200)]
    selected_indices: tuple[Index, ...] = ()
    selected_labels: tuple[NonEmptyText | None, ...] = ()
    selected_texts: tuple[NonEmptyText, ...] = ()
    answer_text: Annotated[NonEmptyText, Field(max_length=12000)] | None = None
    blank_answers: Annotated[tuple[Annotated[NonEmptyText, Field(max_length=2000)], ...], Field(max_length=20)] = ()

    @model_validator(mode="after")
    def validate_answer_shape(self) -> "AnswerResult":
        if self.question_type in (QuestionType.FILL_BLANK, QuestionType.SHORT_ANSWER):
            if any(value is not None for value in (self.selected_index, self.selected_label, self.selected_text)) or (
                    self.selected_indices or self.selected_labels or self.selected_texts):
                raise ValueError("主观题不能混用选项答案字段。")
            if self.question_type == QuestionType.FILL_BLANK:
                if not self.blank_answers or self.answer_text is not None:
                    raise ValueError("填空答案必须使用非空 blank_answers，不混用 answer_text。")
            elif self.answer_text is None or self.blank_answers:
                raise ValueError("简答和解答题必须使用 answer_text，不混用 blank_answers。")
        elif self.question_type == QuestionType.MULTIPLE_CHOICE:
            if not self.selected_indices:
                raise ValueError("多选答案必须选择至少一个选项。")
            if len(self.selected_indices) != len(self.selected_labels) or len(self.selected_indices) != len(self.selected_texts):
                raise ValueError("多选索引、标签和文本数量必须一致。")
            if any(value is not None for value in (self.selected_index, self.selected_label, self.selected_text)):
                raise ValueError("多选答案不能混用单值答案字段。")
        else:
            if self.selected_indices or self.selected_labels or self.selected_texts:
                raise ValueError("非多选答案不能包含多选字段。")
            if self.selected_text is None:
                raise ValueError("非多选答案必须包含 selected_text。")
            if self.question_type in (QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE) and self.selected_index is None:
                raise ValueError("单选/判断答案必须包含 selected_index。")
        if self.question_type not in (QuestionType.FILL_BLANK, QuestionType.SHORT_ANSWER) and (
                self.answer_text is not None or self.blank_answers):
            raise ValueError("选择或判断答案不能混用主观题字段。")
        if len(self.selected_indices) != len(set(self.selected_indices)):
            raise ValueError("多选索引不能重复。")
        return self


class AnswerValidationError(ValueError):
    """题目与答案不一致，消息只包含固定说明。"""


def validate_answer_against_question(question: Question, answer: AnswerResult) -> AnswerResult:
    """严格拒绝矛盾字段；index 是选项标识，不是列表下标。"""
    try:
        question = Question.model_validate(question.model_dump(mode="python", warnings=False))
    except (ValidationError, AttributeError, TypeError):
        raise AnswerValidationError("题目结构无效。") from None
    try:
        # Provider 也可能返回 model_copy/model_construct 的未校验对象；先拒绝缺项、
        # 数组长度不一致和重复项，避免 zip 截短或 set 去重掩盖错误。
        answer = AnswerResult.model_validate(answer.model_dump(mode="python", warnings=False))
    except (ValidationError, AttributeError, TypeError):
        raise AnswerValidationError("答案结构无效。") from None
    if question.question_type != answer.question_type:
        raise AnswerValidationError("答案题型与原题不一致。")
    if question.question_type in (QuestionType.FILL_BLANK, QuestionType.SHORT_ANSWER):
        if question.options or (question.question_type == QuestionType.FILL_BLANK and (
                question.blank_count is None or len(answer.blank_answers) != question.blank_count)):
            raise AnswerValidationError("主观题答案结构或填空数量与原题不一致。")
        if question.question_type == QuestionType.SHORT_ANSWER and question.blank_count is not None:
            raise AnswerValidationError("简答和解答题不能包含填空数量。")
        return answer
    if question.question_type == QuestionType.MULTIPLE_CHOICE:
        options = {option.index: option for option in question.options}
        for index, label, text in zip(answer.selected_indices, answer.selected_labels, answer.selected_texts):
            option = options.get(index)
            if option is None:
                raise AnswerValidationError("多选答案包含不存在的 index。")
            if label != option.label or text != option.text:
                raise AnswerValidationError("多选答案的 label/text 与原题选项不一致。")
        # 先严格验证模型对应关系，再按 Question 中的位置规范化，而非按 index 数值排序。
        chosen = set(answer.selected_indices)
        ordered = [option for option in question.options if option.index in chosen]
        return answer.model_copy(update={
            "selected_indices": tuple(option.index for option in ordered),
            "selected_labels": tuple(option.label for option in ordered),
            "selected_texts": tuple(option.text for option in ordered),
        })
    option = next((item for item in question.options if item.index == answer.selected_index), None)
    if option is None:
        raise AnswerValidationError("答案 selected_index 不存在于原题选项。")
    if answer.selected_label != option.label:
        raise AnswerValidationError("答案 selected_label 与原题选项不一致。")
    if answer.selected_text != option.text:
        raise AnswerValidationError("答案 selected_text 与原题选项不一致。")
    return answer


def format_answer(answer: AnswerResult) -> str:
    """显示字母或实际文本，保留模型对象中的完整答案。"""
    if answer.question_type == QuestionType.FILL_BLANK:
        value = '\n'.join(f"第 {index} 空：{text}" for index, text in enumerate(answer.blank_answers, 1))
    elif answer.question_type == QuestionType.SHORT_ANSWER:
        value = answer.answer_text
    elif answer.question_type == QuestionType.MULTIPLE_CHOICE:
        value = "、".join(label if label is not None else text
                         for label, text in zip(answer.selected_labels, answer.selected_texts))
    else:
        value = answer.selected_label if answer.selected_label is not None else answer.selected_text
    return f"答案：{value}"


class VisionAnalysisResult(SchemaModel):
    """一次图片请求同时返回识题结果和答案，沿用统一一致性规则。"""

    question: Question
    answer: AnswerResult

    @model_validator(mode="after")
    def validate_vision_result(self) -> "VisionAnalysisResult":
        if self.question.source_type != SourceType.VISION:
            raise ValueError("Vision 识题来源必须为 VISION。")
        if len(self.question.question_text) > 8000 or len(self.question.options) > 50 or any(
                len(option.text) > 2000 for option in self.question.options):
            raise ValueError("Vision 题目超过长度或选项数量限制。")
        if [option.index for option in self.question.options] != list(range(len(self.question.options))):
            raise ValueError("Vision 选项 index 必须按视觉顺序从 0 连续编号。")
        # 模型保持冻结；仅在构造校验阶段写入已验证的规范顺序答案。
        object.__setattr__(self, "answer", validate_answer_against_question(self.question, self.answer))
        return self


class VisionBatchResult(SchemaModel):
    """同一截图的完整题组；数组顺序即屏幕阅读顺序。"""

    results: Annotated[tuple[VisionAnalysisResult, ...], Field(min_length=1, max_length=10)]

    @model_validator(mode="after")
    def reject_duplicate_questions(self) -> "VisionBatchResult":
        # 同一题可能被重复排版，也可能有不同编号；仅拒绝完全相同的识别结果。
        identities = [item.question.model_dump_json() for item in self.results]
        if len(identities) != len(set(identities)):
            raise ValueError("同一截图不能重复返回完全相同的题目。")
        return self
