# 题目协议与提取细节

这里记录题目与答案的字段约束、归一化和输入适配器行为。运行路径和更新机制见 [架构](ARCHITECTURE.md)。

## 数据结构与一致性策略

`schemas.py` 使用 Pydantic v2，拒绝未知字段；题目与选项不可变。内部 options 用 tuple，序列化为标准 JSON 数组。原始文本不做 trim/改写，仅拒绝空白字符串。

```json
{
  "question_text": "法国的首都是哪里？",
  "question_type": "single_choice",
  "source_type": "MANUAL",
  "options": [
    {"index": 0, "label": "A", "text": "巴黎"},
    {"index": 1, "label": "B", "text": "伦敦"}
  ]
}
```

```json
{
  "question_type": "single_choice",
  "selected_index": 0,
  "selected_label": "A",
  "selected_text": "巴黎",
  "confidence": 0.99,
  "short_reason": "巴黎是法国首都。"
}
```

单选和多选至少两个选项，判断题恰好两个；index 是唯一非负整数，可以不连续，非空 label 不能重复。单选/判断答案必须有 selected_index 和 selected_text。confidence 为 0～1 的有限数字，short_reason 最长 200 字符。

QuestionType 包含 single_choice、multiple_choice、true_false、fill_blank、short_answer，五种均可进入求解；解答、计算和论述归入 short_answer。SourceType 保持 DOM、VISION、MANUAL。多选使用 selected_indices、selected_labels、selected_texts 三个等长数组；单选/判断保留原单值字段。填空只用 blank_answers 且长度精确匹配 Question.blank_count（1～20），简答/解答只用 answer_text（1～12000字符），两类主观题 options=[]，主客观答案字段不能混用。short_reason 始终只是最多200字符的简要说明。

`validate_answer_against_question` 以原 Question 为事实来源：题型、index、label、text 必须一致。index 按选项标识查找，而不是当作数组下标。对不存在的 index、错误 label/text 一律报 AnswerValidationError，**不自动纠正**，因为修正可能掩盖模型实际选错选项的问题。

无字母选项的 label 和 selected_label 都为 null，绝不生成 A/B/C/D。`format_answer` 有 label 时显示“答案：A”，没有 label 时显示实际文本，保留内部 index/text。

## 模型响应解析

`llm/prompts.py` 集中管理文本和图片分析的 JSON 提示词。`llm/parsing.py` 接受完整 JSON 对象、完整 JSON 代码围栏或前后附合计不超过 200 字符的说明文字。多个对象、重复键、数组包装和非法数字会被拒绝。兼容接口使用 Chat Completions，无须服务端提供 `response_format` 或 JSON Schema 能力。

Windows SDK 关闭自动重试，每次调用结束关闭客户端。认证、限流、超时、断网和协议错误各有固定提示。超时设置约束网络阶段，实际总等待时间还取决于 DOM 题数和连接过程。

## 窗口截图与视觉响应

```text
F8 → Lock / debounce → 立即记录前台 HWND、进程标识与物理边界
   → CAPTURING → 只截该窗口的可见矩形（内存 PNG）
   → ANALYZING → 同一个 Provider 的一次图片请求
   → VisionAnalysisResult {question, answer} → 一致性验证 → 显示 → READY
```

`capture/screen.py` 使用 ctypes 获取 Windows 前台窗口。当前线程临时设为 Per Monitor V2 DPI 感知，优先读取 DWM 的可见物理边界，失败时使用 DPI 感知的 GetWindowRect；完成后恢复原线程上下文。mss 在工作线程内创建并关闭。支持负坐标显示器；不自动切换前台。窗口快照包含 HWND、PID、物理边界和内存中的标题；标题不打印、不作为匹配依据、不单独上传。

触发时先记录目标再打印状态，截图前后再次核对 HWND、进程标识和边界。窗口切换、移动、关闭或越出虚拟桌面时拒绝本次截图，不回退到全屏。最多接受 3200 万原始像素，最长边默认 2048，编码 PNG 上限 8 MiB；超出限制请缩小窗口或适当调整 IMAGE_MAX_EDGE。多屏留白、置顶浮层、通知或其他遮挡仍可能进入屏幕区域截图；它不是后台窗口渲染捕获，请保持题目完整可见。

VisionAnalysisResult 结构：

```json
{
  "question": {
    "question_text": "法国的首都是哪里？",
    "question_type": "single_choice",
    "source_type": "VISION",
    "options": [
      {"index": 0, "label": null, "text": "巴黎"},
      {"index": 1, "label": null, "text": "伦敦"}
    ]
  },
  "answer": {
    "question_type": "single_choice",
    "selected_index": 0,
    "selected_label": null,
    "selected_text": "巴黎",
    "confidence": 0.99,
    "short_reason": "巴黎是法国首都。"
  }
}
```

Vision 强制 source_type=VISION，index 按视觉顺序从 0 连续编号，复用严格 label/text/index 一致性校验。图中圆圈不视为字母标签。视觉提示词要求按屏幕阅读顺序返回所有完整可见的五种题型，最多 10 道，顶层 results 数组每项独立包含 question/answer；旧单题响应继续兼容。整批校验通过后原子发布，任一题答案矛盾或填空数量不匹配会拒绝整批；没有完整可读题时返回固定错误。结构一致并不证明图片识别、知识答案或推导正确，需人工核对。

`vision.py` 串联截图与 Provider；`supports_vision=false` 在截图与请求前报错。BUSY 时不会记录新的目标、截图或并发发请求。ESC 阻止新任务；已经进行的同步 API 请求需等待完成/超时，随后丢弃待显示答案并清理退出。

## DOM 提取与选项解析

```text
F8 → TaskRunner Lock / debounce → EXTRACTING
   → BrowserSession 专用线程 → BrowserDOMAdapter → Question(source_type=DOM)
   → 已有 answer_question → AnswerResult → 一致性验证 → format_answer → READY
```

`browser_session.py` 启动独立临时 context，不接管个人浏览器、不使用用户 profile。Playwright 由同一专用 asyncio 线程持有，事件循环在 READY 空闲期间持续处理导航和 route 回调；对外保留同步接口，并串行执行取题操作，避免每次 F8 新建工作线程违反 Playwright 线程归属。只允许内置 Demo 文件的页面请求；无 HTTP 服务。`capture/browser.py` 和只读 `capture/dom_extract.js` 提取当前渲染 DOM，不调用模型、不操作答案；`dom.py` 复用既有 Text Provider。Fake 严格匹配四道 DOM Demo（两道单选、一道多选、一道判断），保留原 MANUAL 示例，不对任意题目伪装推理。

识别综合 fieldset/legend、role、label/for、ARIA 名称、input type、name/form、父子关系和可见文字。删除所有 Demo data 属性仍能识别四题。隐藏元素和隐藏文字被排除；生产批提取按屏幕顺序读取最多 10 道完整题，题组边界不可靠时拒绝整批。旧单题提取接口保留唯一聚焦或 current 标记选择，否则拒绝多组歧义。动态 JavaScript 更新后的内容在下次 F8 重新读取。

选项按 DOM 顺序从 index=0 编号。`A. 巴黎`、`A、巴黎`、`A．巴黎`、`(A) 巴黎` 提取明确前缀；仅空格形式 `A 巴黎` 要求全组选项存在连续 A/B/C… 佐证。无法确定时保留完整文本和 label=null，`C`、`C language` 不擅自拆成字母标签。普通 radio 推断 single_choice，checkbox 推断 multiple_choice，两项明显“正确/错误”等 radio 推断 true_false；显式题型标记冲突则报错。

### 支持范围

受管理 DOM 适配器读取主文档中有可靠语义的题组。普通浏览器扩展另支持有限的同源 iframe 和开放 Shadow DOM。提取会检查视口完整性，但可能无法判断 CSS 背景图、遮挡或自绘内容是否属于题意。主观题有必要的 Canvas、图片或 SVG 材料时，提取会拒绝只取文字。填空还需要可靠的空数和题型，作答框的已有内容不会被读取。[架构](ARCHITECTURE.md) · [隐私说明](../PRIVACY.md)。

### 答案协议与规范化

single_choice / true_false 使用原有 selected_index、selected_label、selected_text。判断题保留原始选项文字（正确/错误、是/否、True/False 等），不转换成 Python bool；有真实标签时显示标签，否则显示文本。

multiple_choice 使用非空、无重复的 selected_indices，以及等长且逐项对应的 selected_labels / selected_texts。允许只有一个选中项。示例：

```json
{
  "question_type": "multiple_choice",
  "selected_indices": [0, 1, 3],
  "selected_labels": [null, null, null],
  "selected_texts": ["Python", "C", "Java"],
  "confidence": 0.98,
  "short_reason": "Python、C 和 Java 是编程语言。"
}
```

多选的单值字段必须省略或为 null；单选/判断的多值字段必须省略或为空数组。为兼容既有 AnswerResult 对象和默认序列化，字段都保留：selected_text 对多选默认为 null，但对单选/判断仍通过题型校验强制要求非空文本。其余单值字段默认 null，多值字段默认空元组（JSON 数组）。不接受以旧单选答案格式回答多选。

先用 Schema 拒绝空选择、重复索引、数组长度不一致及单值/多值混用，再以 Question 为事实来源核对每个 index、label、text。原 label=null 时不能生成字母。全部一致后才按 Question.options 中的顺序规范化：例如 [3,0,1] 及其正确对应的标签/文本变为 [0,1,3]；不是按 index 数字排序，也不会根据错误文本猜答案。校验函数返回规范化后的新答案，原输入保持不变；文本和 Vision 工作流都使用该返回值。

显示规则：有字母多选显示“答案：A、B、D”，无字母显示“答案：Python、C、Java”；混合标签时每项分别使用其真实 label 或 text。判断题显示“答案：正确”，有真实 A 标签则显示“答案：A”。
