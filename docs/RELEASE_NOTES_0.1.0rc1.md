# AutoQuestion 0.1.0rc1

Windows 上的第一个公开 Release Candidate，按 Python 源码项目分发。**Pre-release，尚非 Stable。**

## 这一版包含什么

- F8 分析当前题目，ESC 退出；处理完回到 READY，支持 BUSY 和去抖。
- 支持单选、多选、判断，保留原始选项文字。
- Vision、AUTO 路由和可选的本地 DOM Demo；普通 AUTO 启动不弹浏览器，测试 DOM 时使用 `--open-demo`。
- 首次配置向导，DeepSeek、Kimi、GLM、OpenAI、自定义 OpenAI-compatible 和 Offline Demo。
- Windows Credential Manager 或 session-only Key，以及本地 Doctor。
- 修复 Setup 中 URL / Model ID 填反后延迟报错的问题：出错字段立即重问，旧配置和最终配置使用相同离线校验，不联网验证 Key。

## 安装与测试

从 [README Quick Start](https://github.com/billstar0128-jpg/AutoQuestion#quick-start) 克隆完整源码，在 Windows 上创建新虚拟环境、安装 requirements.txt，再运行 main.py。
没有 Key 时可选择 Offline Demo。普通 AUTO / Vision 不需要 Chromium runtime；本地 DOM Demo 需安装 Playwright Chromium。

本机已验证 CPython 3.14.6；Windows GitHub CI 已通过 3.10.11 / 3.12.10 / 3.14.7。真实 GitHub 新克隆的安装、首次 Setup 和完整回归已通过。详细结果见 [Actions](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/ci.yml) 和 [M14 验证记录](https://github.com/billstar0128-jpg/AutoQuestion/blob/main/docs/VALIDATION_M14.md)。
测试方法见 [Development](https://github.com/billstar0128-jpg/AutoQuestion/blob/main/docs/DEVELOPMENT.md)。

## 已知限制

- 不自动点击、勾选、提交或翻题。
- DOM 仅用于本项目受管理的本地 Demo，不接管个人浏览器，不保证支持所有网站。
- 不支持 OCR、原生 Anthropic、填空/简答完整求解。
- 没有 EXE、MSI、wheel 或 PyPI 包；本次仅使用 GitHub 自动提供的源码归档。
- 图片能力取决于你配置的具体模型。结构校验不能保证模型答案正确。
- 没有遥测或开发者服务器；题目文本或目标窗口图片发送给你选择的 Provider。
- 同步 API 请求期间退出可能需要等待请求完成或超时。

已有 config_version=1 配置无需迁移。API 根地址和模型标识需分别填写；无效旧配置会提示重新设置，程序不会静默交换字段或改写旧凭据。

## 反馈与许可证

欢迎通过 [Issues](https://github.com/billstar0128-jpg/AutoQuestion/issues) 报告安装、识别或使用中的问题；不要附带 Key、私人截图或原始敏感日志。
安全问题使用 [私密报告](https://github.com/billstar0128-jpg/AutoQuestion/security/advisories/new)。
许可证为 Apache-2.0。正式 v0.1.0 Stable 将另行决定。
