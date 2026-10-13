# AutoQuestion v0.2.1

这次把网页界面交付成能直接使用的 Windows App，修正上一版在线预览容易被当作实际配置入口的问题。

- 提供 Windows x64 便携 ZIP：完整解压后双击 AutoQuestion.exe，不需要 Python 或 PowerShell。
- 本机界面可配置服务商、URL、模型与 API Key，启动／停止答题并查看真实结果。
- 在线页面改为 App 下载入口；配置在本机 App 中完成。
- 复用已有 AUTO / DOM / Vision、F8 / ESC 与 Windows 安全凭据存储。
- API Key 不回传保存值，不进入普通 JSON。截图只在内存中处理。

下载 AutoQuestion-0.2.1-Windows-x64.zip，完整解压并保留 _internal 文件夹，双击 AutoQuestion.exe。配置模型后点击启动，把题目窗口放到前台，再按 F8。普通 Vision 与固定 Offline Demo 不需要 Chromium；Chrome / Edge DOM 扩展在解压目录的 extension 中。

便携版未做商业代码签名，不要求管理员权限。随包保留 Apache-2.0 与依赖许可证。不保证模型答案准确或所有网页 DOM 兼容，不提供自动点击、提交、OCR 或填空/简答完整求解。官方模型示例不代表已进行真实收费 API 测试。

自动检查与 EXE 自检使用临时配置、自己的热键消息、Fake 答案及本机合成 API；没有使用真实 Key 或私人截图。详细验证见仓库文档。
