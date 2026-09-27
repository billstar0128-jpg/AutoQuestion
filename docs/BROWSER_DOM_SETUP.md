# Browser DOM Setup — 0.2.0

这是可选步骤。WPS、记事本和 PDF 阅读器可以直接用 Vision，不需要浏览器扩展。
仅支持标准 Chrome / Edge（Chromium 116+ 的 MV3 能力）；企业策略、特殊发行版和浏览器内置页面可能禁止注入。

## 1. 安装扩展

先解压完整 AutoQuestion 源码。找到与 main.py 同级的 `extension` 文件夹，其中应有 manifest.json。
保持这个文件夹的位置不变，浏览器后续会从这里加载扩展。

- Chrome：地址栏输入 `chrome://extensions`，打开右上角“开发者模式”，点击“加载已解压的扩展程序”，选择 **extension 文件夹**。
- Edge：地址栏输入 `edge://extensions`，打开“开发人员模式”，点击“加载解压缩的扩展”，选择同一个 **extension 文件夹**。

看到 AutoQuestion Browser DOM 卡片并启用，即已加载。可在浏览器扩展菜单固定图标。
Chrome 和 Edge 要分别加载、分别配对；不要选择项目根目录、ZIP 文件或某个 JS 文件。

## 2. 配对本次运行

关闭旧 AutoQuestion，在项目根目录 PowerShell 中运行：

```powershell
.\.venv-win\Scripts\python.exe main.py --pair-browser
```

设置中的 Input Mode 应为 AUTO 或 DOM。必要时先运行 `main.py --setup` 修改；仅在本机输入 API Key。
程序显示本次 32 位配对码的小窗口。点浏览器中的 AutoQuestion 扩展图标，在密码框输入该码，点“连接”。
扩展和程序显示 `Browser DOM Bridge: connected` 即连接成功。Chrome / Edge 可用同一个本次配对码，程序按真实进程匹配。
配好后关闭配对窗口进入 READY，关闭扩展弹窗，把题目页面放前台再 F8。

配对码不是 API Key。它不写配置、日志、URL 或磁盘，只用于本次内存会话。
重新启动 AutoQuestion、重新加载扩展或浏览器丢弃后台 worker 后，需要重新配对。
若复制配对码，请留意系统剪贴板历史；不要把它放进 Issue、截图或聊天。

## 3. 允许当前题目页面

点开扩展会临时授予当前标签的 activeTab 权限。页面导航后，这份临时权限可能失效。
需要在同一个站点连续使用时，点扩展中的“允许当前站点”，在浏览器提示中批准。
这只请求当前 HTTP / HTTPS 主机的权限，不默认请求所有网站；该主机不同端口也在权限范围内。
需要撤销时，在浏览器扩展详情中修改“网站访问权限”，或移除扩展。
浏览器内置页、扩展商店、内置 PDF viewer、file:// 页面可能拒绝 DOM；无需打开个人浏览器调试端口。

## 4. 测试本地合成页面

另开一个项目根目录 PowerShell，**只提供合成示例目录**：

```powershell
.\.venv-win\Scripts\python.exe -m http.server 8765 --bind 127.0.0.1 --directory examples/browser_dom
```

在 Chrome / Edge 打开 `http://127.0.0.1:8765/single_choice.html`，点扩展并允许当前站点。
关弹窗、保持题目页面前台，按 F8，预期 `Input: Browser DOM`，答案后回 READY。
页面顶部链接可切换多选、判断、无字母选项、噪声、Canvas、同源 iframe、SPA 测试页。
Canvas 应 `Browser DOM unavailable → Fallback: VISION`。Vision 需要真实支持图片的模型；Fake 不支持图片。
有需要可临时在终端设置 `$env:INPUT_MODE='dom'`、`$env:LLM_PROVIDER='fake'`，离线验证与 Demo 相同的合成题，结束后移除这两个环境覆盖项。

## 状态与排错

| 现象 | 检查 |
|---|---|
| waiting / 未连接 | AUTO/DOM 是否启动、是否带 --pair-browser、本次配对码是否有效、扩展是否启用 |
| Bridge unavailable | 关闭旧实例；运行 --doctor；端口 37841 被占用时不要结束不认识的进程 |
| connected 但 F8 走 Vision | 关弹窗，确认当前浏览器已配对；允许当前站点；确认题目与选项在视口中 |
| DOM unavailable | Canvas、图片、缺标签、多道歧义题、跨域 iframe、封闭 shadow 或自绘控件可能只能用 Vision |
| 目标变化 / 连接中断取消 | 稳定前台窗口和标签后重新 F8；程序不会改截新标签 |
| DOM 模式在 WPS 报错 | 这是严格 DOM 模式；用 AUTO / Vision 分析桌面窗口 |
| Chrome 成功但 Edge 失败 | Edge 单独安装并配对；不能只在 Chrome 安装 |
| 扩展更新后不工作 | 在扩展管理页面点重新加载，再配对；已授权站点可保留，无需重设 API Key |

ESC 清理 Python bridge、热键和本次自有 Demo，不关闭你自己的浏览器。
测试 HTTP 服务器在它自己的终端按 Ctrl+C 停止。
详细边界见 [Privacy](../PRIVACY.md)、[Security Model](SECURITY_MODEL.md)、[M15 人工验收](MANUAL_ACCEPTANCE_M15.md)。
