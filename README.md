# AutoQuestion — 跨平台屏幕题目 AI 解析助手

[![Windows CI](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/ci.yml)
[![Android CI](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/android.yml/badge.svg?branch=main)](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/android.yml)
[![License: Apache-2.0](https://img.shields.io/github/license/billstar0128-jpg/AutoQuestion)](LICENSE)
[![GitHub Release](https://img.shields.io/github/v/release/billstar0128-jpg/AutoQuestion?include_prereleases&label=GitHub%20Release)](https://github.com/billstar0128-jpg/AutoQuestion/releases)

AutoQuestion 在 Windows 和 Android 上读取屏幕里的练习题，调用你配置的 AI 模型给出参考答案和解题说明。适合自建题库、非计分练习和经授权的学习场景。Windows 可从已授权的浏览器页面读取题目结构，或让支持图片的模型分析前台窗口；Android 通过悬浮窗发起截图识题。

## 下载

| 平台 | 当前公开版本 | 下载与使用说明 |
| --- | --- | --- |
| Windows x64 | [0.6.0 · 预发布](https://github.com/billstar0128-jpg/AutoQuestion/releases/tag/v0.6.0) | [下载 ZIP](https://github.com/billstar0128-jpg/AutoQuestion/releases/download/v0.6.0/AutoQuestion-0.6.0-Windows-x64.zip) · [Windows 使用说明](docs/WEB_UI.md) |
| Android 8.0 及以上 | [0.6.1 · 预发布](https://github.com/billstar0128-jpg/AutoQuestion/releases/tag/v0.6.1) | [下载 APK](https://github.com/billstar0128-jpg/AutoQuestion/releases/download/v0.6.1/AutoQuestion-0.6.1-Android.apk) · [Android 使用说明](docs/ANDROID.md) |

两端独立编号。上表是 GitHub 已公开的安装包，均标为 Pre-release。Android 0.7.0 是尚未发布的本地验收版。

## 三步开始使用

1. **下载安装。** Windows 右键 ZIP 选择“全部解压”，保留 `_internal` 文件夹，双击 `AutoQuestion.exe`。Android 打开 APK，按系统提示允许当前下载来源安装应用。
2. **配置模型。** Windows 打开“模型与配置”，Android 在首页填写配置。用服务商控制台创建的 API Key，填写 Base URL 和 Model ID。Android 和 Windows 截图模式都需要支持图片输入的模型。[API 配置指南](docs/API_SETUP.md)
3. **开始识题。** Windows 启动识题后，将完整题目放到前台窗口并按 **F8**，按 **Esc** 停止。Android 开启悬浮窗权限，显示 AQ 小方框，点一下并按提示共享屏幕。在 AQ 面板查看结果。

没有题目可试时，可以打开[公开练习页](https://billstar0128-jpg.github.io/AutoQuestion/try-questions.html)。使用真实模型识别练习页也可能产生服务商 API 费用。

## 核心功能

- **结构化读取。** Windows 可用已配对的 Chrome / Edge 扩展读取授权页面上的可见题干与选项。DOM 读取成功时仅发送题目文本。
- **多模态识别。** Windows 可识别前台的 PDF、Office 文档和其他桌面窗口。Android 可分析屏幕截图，Android 11 及以上可按需开启录屏兼容。受保护的内容可能无法捕获。
- **同屏多题。** 支持单选、多选、判断、填空、简答和解答题。AQ 面板逐题展示结果，支持复制。
- **多模型接入。** 可配置 DeepSeek、Kimi、GLM、OpenAI 或其他兼容 OpenAI Chat Completions 的服务。

## 推荐模型及 API 配置

截图识题可从官方明确支持图片的模型开始。API Key 是服务商用来验证请求和计费的密钥，按服务商要求开通 API 计费或充值，仅填入本机 App。

| 服务 | Base URL | 可选 Model ID |
| --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | [`deepseek-flash`](https://api-docs.deepseek.com/guides/vision/) |
| Kimi / Moonshot（中国平台） | `https://api.moonshot.cn/v1` | `kimi-k3.1-pro` |
| 智谱 / GLM | `https://open.bigmodel.cn/api/paas/v4/` | `glm-5.3-flash` |
| OpenAI | `https://api.openai.com/v1` | [`gpt-6-luna`](https://developers.openai.com/api/docs/models/gpt-6-luna) |

模型示例来自官方接口文档，实际可用性取决于账户权限。获取 Key、选择图片模型和查看官方价格的步骤见 [API 配置指南](docs/API_SETUP.md)。

## 技术架构

Windows 使用 Python。AUTO 模式在已配对且获授权的 Chrome / Edge 页面上优先读取 DOM（网页结构），取题失败时可回退为前台窗口截图。其他桌面窗口直接走截图模式。扩展经本机回环连接与应用通信。

Android 使用原生应用，公开版通过系统屏幕共享或可选的录屏兼容服务捕获图像。两端直接向用户指定的模型接口发送输入并解析结果。[架构文档](docs/ARCHITECTURE.md)

## 隐私与使用边界

- 应用无需项目运营的服务器。题目文本或截图会发送至你配置的模型服务商，服务商的数据处理与保留规则适用。
- 应用在内存中处理截图。Windows 可选择凭据管理器或仅本次使用，Android 使用基于 Android Keystore 的加密存储。
- 应用会访问 GitHub 查看公开版本。下载和安装应用更新需要你的操作。
- 请先确认有权读取和发送屏幕内容。应用不会点击、提交或翻题。AI 可能漏题或答错，请核对解题过程和结果。

详见[隐私说明](PRIVACY.md)和[安全政策](SECURITY.md)。

## FAQ

- **安装包打不开或 APK 无法覆盖安装？** 先核对系统要求与安装包来源，同签名 APK 才能覆盖安装。
- **模型配置失败或手机识别时黑屏？** 检查 Key、额度、Model ID、图片能力和屏幕共享范围。系统保护的页面可能无法捕获。
- **为什么网页从 DOM 回退到截图？** AUTO 取不到可靠题目结构时会尝试截图。检查扩展配对、站点授权和页面内容。

安装、识别失败、更新和隐私问题详见 [常见问题](docs/FAQ.md)。

## 开发者文档

- [从源码运行、PowerShell 入门和构建](docs/DEVELOPMENT.md)
- [浏览器扩展安装与配对](docs/BROWSER_DOM_SETUP.md)
- [高级配置](docs/CONFIGURATION.md) · [技术架构](docs/ARCHITECTURE.md) · [安全模型](docs/SECURITY_MODEL.md)
- [贡献指南](CONTRIBUTING.md) · [变更记录](CHANGELOG.md) · [发布检查清单](docs/RELEASE_CHECKLIST.md)

## License

AutoQuestion 的 Windows、Android 和浏览器扩展完整源码按 [Apache-2.0](LICENSE) 开放。

如果 AutoQuestion 对你的学习或开发有帮助，欢迎在 GitHub 点一个 Star。
