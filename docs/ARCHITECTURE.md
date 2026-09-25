# Architecture

```text
main.py → cli → configuration / Setup → app
F8 → TaskRunner (Lock / debounce / BUSY)
   → Input Router → DOM acquisition OR Vision capture
   → Provider → JSON parse → Schema / answer consistency validation
   → format_answer → Console → READY
ESC / Ctrl+C → stop new tasks → join worker → close browser → exit
```

热键在主线程注册与注销，prepare 在任何任务日志前同步记录 F8 目标。TaskRunner 只允许一个 worker，不排队。Provider 同步请求有超时、无自动重试；退出等待当前请求结束/超时，丢弃迟到答案，不能保证瞬时取消。

## Input and browser lifecycle

普通 AUTO 没有 BrowserSession 对象、浏览器线程、Playwright driver 或 Chromium 子进程。`app.py` 只在 DOM 或本次 open-demo 请求时分配会话；不是 F8 时反复尝试启动浏览器。Router 接受 browser=None 并复用原始目标转 Vision。

受管理 BrowserSession 的专用 asyncio 线程始终泵事件；用锁串行执行跨线程操作。只允许两个内置 file:// Demo，阻止其他页面请求、不接管个人 profile。其构造函数本身仍启动事件线程，所以无浏览器启动路径必须连对象都不创建。清理先 join worker，再关闭 Chromium/Playwright，停止 event loop 并 join 会话线程。

AUTO 依次核对本次浏览器 PID、唯一 HWND、唯一 Page、页面焦点与可见性；歧义不读后台 DOM。取题前后核对窗口，Vision 截图前后再次核对。只有 BrowserExtractionError / 无会话 / 无效 DOM Question 可 fallback。Provider、认证、超时、JSON 或答案校验失败不会转成第二次 Vision 请求。

强制 DOM 保留已有行为：从受管理 Demo 取题，不要求前台匹配，也不 fallback。Vision 不读 DOM，即使用户打开了 Demo。固定 demo 只使用 MANUAL 示例题。

## Provider profile and protocol

```text
Provider Profile (brand / editable defaults)
    → Protocol Provider (openai or fake)
    → API request / offline answer
```

注册表与适配器分离。真实请求是 Chat Completions，使用官方 OpenAI Python SDK 的 base_url；Text 与 Vision 共用错误处理、有限 JSON 解析与一致性验证。Vision 一次请求同时返回 Question 与 Answer，不追加文本请求。Model supports_vision 是本次模型配置，不是品牌属性。

## Configuration and secrets

Process environment > explicit `--env-file` > saved AppData config > defaults。不会自动加载 `.env`。Config 的兼容默认仍为 fake/vision；无完整配置的交互首次启动由 Setup 接管，API 向导推荐 AUTO。

UserConfig 只含非秘密字段与凭据引用。Key 优先来自显式配置，其次向导 session-only 或保存的 Credential Manager 引用。RuntimeSettings / Config 携带隐藏 repr 的 LLMConfig，不把安全存储加载的 Key 写回 os.environ。open_demo 只在 RuntimeSettings 或 CLI 内存在，不进入 config.json。

凭据更新为 copy-on-write：先创建新安全引用，再原子替换普通配置；失败回收本次新引用，保留旧凭据。Doctor/show-config 只检查元数据，正常启动才读取选定 Key。更完整的限制见 [Security Model](SECURITY_MODEL.md) 和 [Configuration](CONFIGURATION.md)。

## Source map

| Module | Responsibility |
|---|---|
| cli / startup / setup_wizard | 管理入口、合并配置、首次向导和本次 Demo 选择 |
| config / user_config / credentials / secret_input | 校验、原子存储、安全凭据、遮罩输入 |
| app / hotkeys | 状态机、worker、Windows 热键生命周期 |
| router / browser_session / capture | 只读输入、窗口身份保护、内存 PNG |
| schemas / llm / dom / vision / demo | 题目协议、求解请求和输出 |
| doctor / secret_safety | 本地只读诊断，无业务副作用 |

实现边界、Schema 细节与演进记录见 [Development](DEVELOPMENT.md)。
