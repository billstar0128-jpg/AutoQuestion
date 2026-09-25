# Technical Notes

从 M1–M12 README 保留的协议和实现细节。当前启动及验收命令以 [README](../README.md) 和 [M13 Acceptance](MANUAL_ACCEPTANCE_M13.md) 为准。Canvas 手动验收须用 --open-demo；普通 AUTO 不自动启动浏览器。

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

QuestionType 包含 single_choice、multiple_choice、true_false、fill_blank、short_answer；前三种支持求解，填空/简答仍仅预留。SourceType 保持 DOM、VISION、MANUAL。多选使用 selected_indices、selected_labels、selected_texts 三个等长数组；单选/判断保留原单值字段。M10 协议详见下文。

`validate_answer_against_question` 以原 Question 为事实来源：题型、index、label、text 必须一致。index 按选项标识查找，而不是当作数组下标。对不存在的 index、错误 label/text 一律报 AnswerValidationError，**不自动纠正**，因为修正可能掩盖模型实际选错选项的问题。

无字母选项的 label 和 selected_label 都为 null，绝不生成 A/B/C/D。`format_answer` 有 label 时显示“答案：A”，没有 label 时显示实际文本，保留内部 index/text。

## Provider 架构

以下为保留的文本 Demo 流程；Vision 使用同一 Provider 的 analyze_image 方法，共用 SDK 请求、错误映射和解析基础设施。

```text
F8 → TaskRunner（Lock / debounce / BUSY）
   → demo.py（固定 MANUAL Question）
   → BaseLLMProvider.answer_question
      ├─ FakeLLMProvider：离线预置答案，仅接受内置示例题
      └─ OpenAICompatibleProvider：官方 SDK 文本请求
   → JSON 解析 → AnswerResult → Question 一致性验证
   → format_answer / 控制台 → READY
```

- `main.py`：源码启动入口。
- `config.py`：热键配置与独立的 LLMConfig，真实 Provider 按需加载，SecretStr 隐藏 Key 的打印表示。
- `app.py`：生命周期和单工作线程，增加同步 prepare 在日志前记录目标，已知业务错误展示固定消息，未知异常隐藏原始内容后恢复。
- `hotkeys.py`：保持上一阶段 Windows 原生注册/注销与 MOD_NOREPEAT。
- `schemas.py`：数据定义、业务一致性验证和答案显示。
- `demo.py`：保留固定 MANUAL 题目的文本集成。
- `llm/base.py`：answer_question 文本接口、默认拒绝的 analyze_image 能力及少量错误类型。
- `llm/prompts.py`：集中管理 Text 与 Vision 的 JSON 协议提示词。
- `llm/parsing.py`：解析完整 JSON、完整 json 代码围栏、前后合计不超过 200 字符的说明文字；拒绝多对象、重复键、数组包装、非法数字或不可恢复输出。
- `llm/openai_compatible.py`：base_url、超时、错误映射与资源关闭；不要求 response_format/json_schema 等高级服务端能力。
- `llm/fake.py`：只服务固定示例，不能用于推理任意问题。

SDK 关闭自动重试，以免重复请求和扩大退出等待；每次调用结束都会关闭客户端。API 认证失败、限流、超时、断网和协议错误转换成清晰异常。真实请求期间 ESC 会停止接受新任务，等待当前同步请求结束/超时，再清理退出；超时是网络阶段超时，不是绝对总时长上限。Fake 模式的等待可立即中断。

## Vision Mode（Milestone 6）

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

Vision 强制 source_type=VISION，index 按视觉顺序从 0 连续编号，复用严格 label/text/index 一致性校验。图中圆圈不视为字母标签。Prompt 只选择主要、完整的一道单选、多选或判断题；无法可靠识别时返回固定错误协议，程序提示调整窗口后重试。结构一致并不证明图片识别和知识答案正确，需人工核对。

`vision.py` 串联截图与 Provider；`supports_vision=false` 在截图与请求前报错。BUSY 时不会记录新的目标、截图或并发发请求。ESC 阻止新任务；已经进行的同步 API 请求需等待完成/超时，随后丢弃待显示答案并清理退出。

### Adapter 与线程归属

```text
F8 → TaskRunner Lock / debounce → EXTRACTING
   → BrowserSession 专用线程 → BrowserDOMAdapter → Question(source_type=DOM)
   → 已有 answer_question → AnswerResult → 一致性验证 → format_answer → READY
```

`browser_session.py` 启动独立临时 context，不接管个人浏览器、不使用用户 profile。Playwright 由同一专用 asyncio 线程持有，事件循环在 READY 空闲期间持续处理导航和 route 回调；对外保留同步接口，并串行执行取题操作，避免每次 F8 新建工作线程违反 Playwright 线程归属。只允许内置 Demo 文件的页面请求；无 HTTP 服务。`capture/browser.py` 和只读 `capture/dom_extract.js` 提取当前渲染 DOM，不调用模型、不操作答案；`dom.py` 复用既有 Text Provider。Fake 严格匹配四道 DOM Demo（两道单选、一道多选、一道判断），保留原 MANUAL 示例，不对任意题目伪装推理。

识别综合 fieldset/legend、role、label/for、ARIA 名称、input type、name/form、父子关系和可见文字。删除所有 Demo data 属性仍能识别四题。隐藏元素和隐藏文字被排除；多个题组只有唯一聚焦或明确 current 标记时才选择，否则报错，不猜第一题。动态 JavaScript 更新后的内容在下次 F8 重新读取。

选项按 DOM 顺序从 index=0 编号。`A. 巴黎`、`A、巴黎`、`A．巴黎`、`(A) 巴黎` 提取明确前缀；仅空格形式 `A 巴黎` 要求全组选项存在连续 A/B/C… 佐证。无法确定时保留完整文本和 label=null，`C`、`C language` 不擅自拆成字母标签。普通 radio 推断 single_choice，checkbox 推断 multiple_choice，两项明显“正确/错误”等 radio 推断 true_false；显式题型标记冲突则报错。

### 范围、隐私与测试

DOM Adapter 仅支持有可靠语义关联的当前主文档题组，不宣称通用网站识别。不处理 iframe、Shadow DOM、canvas、仅图片题或任意个人浏览器；可见性排除隐藏内容，但不模拟视口遮挡和裁切。强制 dom 模式遇到无题、标签缺失、多组歧义、连接失效时返回 BrowserExtractionError，任务恢复 READY，不回退。单选、多选和判断均调用现有 Provider。AUTO 的严格回退规则见 [Architecture](ARCHITECTURE.md)。

DOM 提取不读取 Cookie、浏览器存储、密码/input value、认证请求头或整页源码。只将局部结构化题干和选项交给既有 Provider；页面/底层异常不会原样写入日志，未记录 URL、标题或 profile。控制台显示题干和答案，没有新增历史存储。

`test_browser.py` 用真实 headless Chromium 验证四题、无专用属性、ARIA、动态渲染、隐藏内容排除、歧义/关闭/断连及线程清理。`test_dom.py` 验证真实 DOM→Fake/SDK MockTransport、错误后 READY/再次触发、BUSY/退出、入口清理及默认 Vision 保持。测试中仅为模拟用户翻题而点击导航按钮，生产提取代码没有点击操作。完整测试需先安装 Chromium，原有 Windows 热键测试仍需无其他实例占用 F8/ESC。自动测试不代表物理热键与可见界面人工验收已完成。

参考：[Playwright Python 安装和线程说明](https://playwright.dev/python/docs/library)、[浏览器 runtime](https://playwright.dev/python/docs/browsers)、[页面 JavaScript 求值](https://playwright.dev/python/docs/evaluating)。

### Canvas 导航修复（M9 人工验收）

旧会话使用同步 Playwright + 按需执行的线程池：READY 时线程不运行 Playwright 事件循环，手动点击 Canvas 链接产生的导航被 route 拦截后一直等待 Python 放行。此前测试直接调用 goto，恰好驱动了事件分发，未覆盖空闲时的手动导航。两个 file:// 文件的允许规则和 Canvas 内联脚本本身正确，页面不存在“加载中”占位文本替换逻辑。

修复让浏览器专用线程持续运行 asyncio 事件循环，并使用异步 Playwright 处理 route；没有添加轮询 sleep、延长 timeout 或放宽文件允许列表。Router、F8/ESC、Schema 和 Provider 行为不变。`test_idle_navigation.py` 在浏览器中安排稍后点击真实导航链接，随后完全不调用 Playwright，验证独立完成 load、readyState=complete、完整题干/四个选项绘图，以及返回 DOM。Windows 冒烟测试也改为这条点击路径，并通过 TaskRunner 验证 DOM→Canvas fallback→DOM。

重新验收需先 ESC 退出旧实例，再在 AUTO 模式使用 main.py --open-demo 启动；在 READY 时手动打开 Canvas，无需再按 F8“解卡”，应直接显示完整行星题。随后 F8 应 DOM unavailable→Fallback: VISION；手动返回 DOM 后 F8 应 Input: DOM。真实 Vision 验收仍需启用图像能力的模型；Fake 不支持图片。自动测试只用合成图片和 Mock Provider。


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

### Text / Vision / AUTO

Text 和 Vision 共用题型答案协议提示词，要求只返回 JSON、只能选择已有选项、保持 null 标签、多选返回全部认为正确的选项且不预设至少两项。Vision 一次图像请求同时提取 Question 并给出答案：checkbox/明确多选识别为 multiple_choice，明显判断题识别为 true_false，保留来源 VISION。

DOM 的多选/判断现在直接送入现有 answer_question。AUTO 仍仅在 acquisition failure 时 fallback；任何题型的 Provider、JSON、答案结构或一致性错误都 ERROR→READY，不能再次请求 Vision。DOM 成功时不截图。结构校验不能证明模型知识判断正确，仍需人工核对。
