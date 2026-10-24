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

普通 AUTO / DOM 不创建 BrowserSession、Playwright driver 或 Chromium 子进程。`app.py` 只在 open-demo 请求时分配受管理会话。AUTO / DOM 启动本机 BrowserBridge；Vision / 固定 demo 不启动 bridge。端口不可用不阻止 AUTO 的 Vision。

受管理 BrowserSession 的专用 asyncio 线程始终泵事件；用锁串行执行跨线程操作。只允许两个内置 file:// Demo，阻止其他页面请求、不接管个人 profile。其构造函数本身仍启动事件线程，所以无浏览器启动路径必须连对象都不创建。清理先 join worker，再关闭 Chromium/Playwright，停止 event loop 并 join 会话线程。

AUTO 依次核对本次浏览器 PID、唯一 HWND、唯一 Page、页面焦点与可见性；歧义不读后台 DOM。取题前后核对窗口，Vision 截图前后再次核对。只有 BrowserExtractionError / 无会话 / 无效 DOM Question 可 fallback。Provider、认证、超时、JSON 或答案校验失败不会转成第二次 Vision 请求。

严格 DOM 同样要求前台目标匹配，支持受管理 Demo 与普通浏览器扩展；桌面窗口或提取失败报错，不 fallback。Vision 不读 DOM，即使用户打开了 Demo。固定 demo 只使用 MANUAL 示例题。

## General Browser DOM — 0.2.0

F8 prepare 在日志前保存 HWND/PID/物理边界，用 QueryFullProcessImageNameW / GetProcessTimes 保存可执行路径与进程创建时间。BrowserClassifier 仅按可执行文件 basename 识别 chrome.exe/msedge.exe，不猜标题。受管理 PID 优先；其他桌面进程直接 Vision，不尝试 DOM。

扩展 WebSocket 连接固定 127.0.0.1:37841/bridge。websockets 15 同步 server 使用独立线程、64 KiB 消息上限、有限队列、握手/取题超时、无压缩和隔离 logger。每次启动生成 192-bit 配对码，--pair-browser 本地 Tk 窗口显示；不持久化、不自动启动浏览器。退出先结束任务，再关闭连接和服务器线程。

握手校验 extension Origin、Host、路径及配对码。GetExtendedTcpTable 找到精确 localhost client tuple PID；同一映像的 network-service 子进程沿创建时间有效的父链匹配浏览器根进程。Chrome 与 Edge 不互相代替；同进程多份可用会话视为歧义。

扩展事件只更新 window/tab ID 与递增 epoch。F8 固定会话和状态，请求携带随机 request ID 与原 epoch/window/tab；worker 取题前后核对当前 focused window / active tab。只有 F8 请求通过 scripting 注入 isolated-world 提取器，不配置常驻 content_scripts。目标变化抛 CaptureError；只有 acquisition failure 才 fallback。配对浏览器的 fallback 在截图前后额外做 metadata-only check；断连而不能证明原标签时取消，不截新标签。

提取器限定节点、文字和选项预算，使用可见语义题组、legend/heading/ARIA、radio/checkbox 标签，保留原始选项并进入既有 Question/Answer 协议。歧义、缺标签、Canvas 仅图片等返回 unavailable。同源 iframe/open shadow 有限遍历；不绕过跨域/closed shadow 权限，不写控件、不提交。

权限为 activeTab/scripting 及用户主动授予的站点权限。OS F8 本身不授予 activeTab，需点击扩展或允许当前站点。worker 被回收、扩展重载或 Python 重启需重配。20 秒协议心跳维持 MV3 生命周期，不轮询 DOM。

参考：[activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab)、[MV3 WebSocket](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets)、[websockets server](https://websockets.readthedocs.io/en/15.0.1/reference/sync/server.html)、[Windows TCP ownership](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedtcptable)。

## Provider profile and protocol

```text
Provider Profile (brand / editable defaults)
    → Protocol Provider (openai or fake)
    → API request / offline answer
```

注册表与适配器分离。真实请求是 Chat Completions，使用官方 OpenAI Python SDK 的 base_url；Text 与 Vision 共用错误处理、有限 JSON 解析与一致性验证。Vision 一次图片请求返回 1～10 个独立 Question/Answer（results 数组），不追加文本请求；兼容旧单题对象。DOM 分别调用 Text Provider，全部验证后一次发布，失败不再转 Vision。Model supports_vision 是本次模型配置，不是品牌属性。

0.4.0 将 `fill_blank` 与 `short_answer` 接入完整流程。主观题 `options=[]`；填空的 `blank_count` 为 1～20，答案用 `blank_answers` 且严格匹配空数；简答/解答用 `answer_text`（最多 12000 字符）。主观答案不能包含选项字段，客观答案不能混入主观字段。`short_reason` 仍为最多 200 字符的简要说明，不代替主观正文。复制以界面主动事件为边界，纯文本直接进入系统 Clipboard；不增加自动输入或页面写操作。

## Android

原生 Java App 使用独立的 HTTPS Chat Completions 客户端，共用同屏多题 JSON 协议，不依赖 Windows 服务。MediaProjection 与 mediaProjection 类型前台服务持有一份捕获会话，悬浮按钮点击后才编码一帧并请求。Android Keystore 保存加密密钥，截图和答案只在内存中。服务停止时释放悬浮窗、VirtualDisplay、ImageReader、MediaProjection 和请求。完整操作与系统限制见 [Android](ANDROID.md)。

## Application updates — 0.5.0

版本检查是独立于 F8 / Provider 的公开 HTTPS 路径，不携带模型配置、Key、题目、答案、截图或本机 UI 会话令牌。两端读取固定 `billstar0128-jpg/AutoQuestion` 的 Releases 列表，不使用会排除测试版的 latest 端点；排除 draft，按数值版本与 alpha/beta/rc 阶段顺序选择更高且适用的平台包。检查失败不阻断答题，下载和安装均由用户主动操作。

GitHub 资产必须具有准确名称、已上传状态、大小和 SHA-256 digest。下载只经固定仓库的 HTTPS 地址与受限 GitHub 资产 CDN，最多五次跳转；不复用 Provider 请求头。有 `SHA256SUMS.txt` 时先校验清单本身，再核对目标包。它验证来源约束和完整性，不代表 GitHub 项目账号永远不会失陷。

Windows `updates.py` 使用独立 worker，下载后检查 ZIP 的原始路径、重复名称、链接与解压预算，写入 `%LOCALAPPDATA%\AutoQuestionApp\` 的新目录。用户停止答题并点击安装后，旧进程有序退出；helper 启动新版，等待其原生窗口携版本/PID 回执，再更新桌面快捷方式。原便携目录和 AppData 配置不覆盖、不删除。源码环境只能检查并手动下载 App，不能自动覆盖源码。

Android Activity 持有独立 UpdateManager，不由悬浮捕获服务轮询。主界面恢复与前台计时触发检查，进入后台会取消正在执行的检查或下载。APK 位于应用私有缓存，交付安装前再次验证哈希、包名、版本名、递增 versionCode、最低系统版本和当前签名；限定的只读 ContentProvider 仅暴露该更新文件，系统安装器仍要求用户授权与确认。

只有安装包和公开更新元数据会写入更新目录/缓存，截图的内存处理策略不变。0.4.0 及更早版本没有更新模块，需要手动安装一次新版本。用法见 [Windows](WEB_UI.md)、[Android](ANDROID.md)，网络披露见 [Privacy](../PRIVACY.md)。

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
| browser_identity / bridge_protocol / browser_bridge | Windows 进程归属、受限协议、认证 loopback 会话 |
| extension | MV3 配对、逐站授权、前台 metadata、按请求只读提取 |
| schemas / llm / dom / vision / demo | 题目协议、求解请求和输出 |
| desktop_app / desktop_instance / web_ui | 原生工作台、单实例、认证本机 UI 和答题生命周期 |
| updates | 独立的 GitHub 版本检查、受限下载/解压和 Windows 更新切换 |
| Android UpdatePolicy / UpdateHttp / UpdateManager / UpdatePackageProvider | 版本与下载约束、APK 验证和系统安装交付 |
| doctor / secret_safety | 本地只读诊断，无业务副作用 |

实现边界、Schema 细节与演进记录见 [Development](DEVELOPMENT.md)。
