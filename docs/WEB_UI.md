# 本机网页工作台

## 普通用户：下载 Windows App

[下载 AutoQuestion-0.3.0-Windows-x64.zip](https://github.com/billstar0128-jpg/AutoQuestion/releases/download/v0.3.0/AutoQuestion-0.3.0-Windows-x64.zip)，右键“全部解压”，保留 _internal 文件夹，双击 AutoQuestion.exe。无需 Python、依赖安装或 PowerShell。App 会打开独立桌面窗口；在这里可以真正输入、保存配置并运行答题。

网站首页只提供 App 下载与说明，API Key 不在网上填写。先前网页是交互预览，无法保存配置；该入口已改成明确的下载页。可选交互预览放在单独的 preview/，其“配置”按钮引导下载 App。

便携 App 未做商业代码签名，不要求管理员权限。下载时可能出现 Windows 未知发布者提示；发布页提供 SHA256 校验文件。许可证与实际依赖的完整许可文本随包附带，包含 Python、PyInstaller 例外说明等。

## 源码用户

完整解压源码后，双击根目录 **AutoQuestion.pyw**。需要标准 Windows Python 3.10 或更新版本；如果 .pyw 没有关联，用 Python Launcher 打开。第一次会以图形窗口询问是否创建 .venv-win 并安装 requirements.txt，后续直接打开独立桌面工作台，不需要日常使用 PowerShell。首次准备需要网络；普通答题不要求安装 Playwright Chromium runtime。

工作台有三个页面：答题工作台、模型与配置、开始使用。无配置时直接显示首次配置；已有配置时读取当前用户的 AppData 配置，已保存 Key 不回传浏览器。点击启动后把题目窗口置前台再按 F8，答案与实际来源会显示在工作台。ESC 停止热键服务并释放资源，控制台保留以便重新启动。点击右上角 × 或“退出本机程序”会停止答题、清空内存记录、关闭本机服务并退出。最小化保持运行，再次双击只唤起已有窗口。正在执行的同步模型请求会完成或超时后清理；保存的配置和安全凭据保留。

离线 Demo 按钮仅本次启用 Fake/MANUAL 示例，不更改已保存的 API 配置。预置答案不代表真实模型能力。受管理 DOM Demo 仍可用原有 --open-demo 命令；需要对应 Chromium runtime。答题运行期间设置不能修改，先停止再保存。

同一屏幕中有多道完整题时，工作台先列出“同屏识别”的各题题干、答案与理由，点击某一题可查看该题的全部选项和置信度。单次最多 10 道；不会自动滚动或翻页，画面过小、裁切或遮挡可能漏题。内置 DOM Demo 可点击“同屏两道题：单选 + 多选”验证，返回普通 Demo 后单题流程继续可用。

三到六道题可以混合单选、多选和判断。首次配置的模型等待时间为 180 秒，可在设置中改到最多 300 秒；旧配置保留原等待时间，题多时请在“模型等待时间”调整后保存。DOM 多题会逐题请求，可能增加等待和 API 用量。处理时不会排队追加请求；Windows 的同步请求停止后会等完成或超时再清理，迟到答案不展示。

## 第一次配置示例

API Base URL 填**服务根地址**，不要附加 /chat/completions，不要填聊天网站地址。Model ID 是服务商定义的模型标识，不是 URL。网页与原有控制台向导共用相同的服务商示例；示例不会自动选择模型或自动启用 Vision。

| Provider | Base URL | 示例模型 ID | 官方文档 |
|---|---|---|---|
| DeepSeek | https://api.deepseek.com | deepseek-flash、deepseek-v4-pro | [Quick Start](https://api-docs.deepseek.com/) |
| Kimi | https://api.moonshot.cn/v1 | kimi-k3、kimi-k2.6 | [Quick Start](https://platform.kimi.com/docs/get-api-key) |
| GLM | https://open.bigmodel.cn/api/paas/v4/ | glm-4.6v、glm-4.6v-flash | [Chat Completions](https://docs.bigmodel.cn/api-reference/模型-api/对话补全) |
| OpenAI | https://api.openai.com/v1 | gpt-4.1-mini、gpt-4.1-mini-2025-04-14 | [模型文档](https://developers.openai.com/api/docs/models/gpt-4.1-mini) |
| Custom | 服务商提供的 OpenAI-compatible API 根地址 | 服务商提供的 ID | 由用户确认 |

官方资料核对日期：2026-10-13。模型列表和账户权限会变化，这不是完整目录，也不代表已进行真实 API 测试。DeepSeek 官方说明 deepseek-flash 支持标准 image_url 图片输入；deepseek-v4-pro 等其他模型的能力需单独确认。[DeepSeek Vision](https://api-docs.deepseek.com/guides/vision/)。

例如使用 DeepSeek 时：选择 DeepSeek → 根地址填 https://api.deepseek.com → Model ID 按账户选择 deepseek-flash 等 → 填平台创建的 API Key → 仅在确认该模型支持图片后勾选图片能力 → 保存 → 启动。不会检测 Key 真伪、联网拉模型或自动发收费测试请求。API 服务通常单独计费。

Key 可选择 Windows 安全凭据保存或仅本次使用。更换 API 地址时必须重新输入 Key；凭据保存不可用时给出明确错误，可由用户选择仅本次使用，不会自动降级为明文保存。旧安全凭据保留，删除仍走原有 --reset-config 的确认流程。

## 本机服务边界

网页控制台只监听 127.0.0.1 的随机端口。内嵌 WebView2 通过 URL fragment 接收本次随机会话令牌，随后从地址栏移除；令牌仅用于本机 API，在该端口的 sessionStorage 中保留以支持刷新。API Key 不存入 localStorage/sessionStorage，不回传已保存的值。API 要求正确 Host 与令牌；写请求还要求同源 Origin、JSON 内容类型和大小限制。没有 CORS 放行、远程登录或云端 API 代理。

题目、答案及最多 20 条本次记录仅保留在本机进程内存中，可主动清空，退出销毁。界面使用 textContent 显示模型文本，不执行其中的 HTML。截图仍在内存中处理，模型请求依旧由原有后端发送给用户配置的服务商。Bridge 配对码仅在用户点击获取时回传到本机界面，30 秒后隐藏，不进入状态接口、记录或配置。

网页启动以界面保存的配置为准，不读取 .env 或覆盖已保存的模型设置；命令行入口仍保留原有环境变量优先级。热键继续使用 F8/ESC。项目不提供 AutoQuestion 账号登录。请只对自己的题库、非计分练习和授权场景使用。

## 在线交互预览与开发

GitHub Pages 首页是 App 下载页，不提供假的在线配置表单。独立 preview/ 才是静态界面预览；禁用 Key 输入与本机操作。实际配置、F8 与模型调用由下载的 App 执行。

开发者也可运行 `main.py --ui`。网站通过 `tools/build_web_preview.py` 导出到被忽略的 dist/site/；Windows App 在 dist/windows/，发布工作流不会把该目录混入网站。前端无需 Node、npm 或第三方 CDN。

## 桌面窗口与运行环境

使用 pywebview / Microsoft Edge WebView2，界面在独立 App 窗口内。WebView 使用私密模式，不接管 Chrome / Edge 个人 profile。缺少 Runtime 时按 [微软官方说明](https://developer.microsoft.com/microsoft-edge/webview2/) 安装。重复启动用当前 Windows 会话和配置路径对应的互斥锁，并通过只含“激活窗口”指令的本机窗口消息唤起已有 App；不把 API Key 或会话令牌放入进程间消息或锁文件。异常退出后锁由 Windows 回收。
