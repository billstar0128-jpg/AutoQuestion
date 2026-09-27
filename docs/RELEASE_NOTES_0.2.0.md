# AutoQuestion v0.2.0

0.1.0rc1 里，AutoQuestion 已经能通过 Vision 读取 WPS、记事本和其他桌面窗口，但普通网页的 DOM 还只存在于项目自己的 Demo Browser。

v0.2.0 把这一块补上了。

现在安装 AutoQuestion Browser Extension 并配对、授权站点后，受支持的 Chrome / Edge 页面在 AUTO 下优先走 DOM：题干和选项从网页结构中提取，再交给文本模型分析；WPS、记事本、PDF 阅读器等桌面程序直接使用 Vision。

如果网页是 Canvas、图片题，或者 DOM 无法可靠提取，AUTO 会退回 Vision。窗口或标签变化时取消任务；取得题目后的 Provider 错误不会再追加图片请求。

Browser → DOM first · Desktop → Vision · DOM unavailable → Vision fallback

## What’s new

- 普通 Chrome / Edge 页面 DOM 支持与可选 MV3 扩展。
- 本机 Browser Bridge、内存配对码和真实进程匹配。
- 前台浏览器 / 桌面程序识别与 AUTO 路由。
- Browser DOM 诊断、合成测试页面、安装文档与隐私安全边界说明。

仍支持单选、多选、判断与无字母选项。DOM 成功不截图。严格 DOM 模式只读前台浏览器 / 受管理 Demo；Vision 模式始终使用 Vision。

## Install and test

按 [README Quick Start](https://github.com/billstar0128-jpg/AutoQuestion#quick-start) 或小白版说明安装 Windows Python 环境与 requirements.txt。普通 Vision 无需扩展；网页 DOM 按 [Browser DOM Setup](https://github.com/billstar0128-jpg/AutoQuestion/blob/main/docs/BROWSER_DOM_SETUP.md) 加载 extension 文件夹。
旧配置无需迁移。受管理本地 Demo 仍通过 --open-demo 启动。
仅提供 Python 源码，不提供 EXE、MSI 或 PyPI 包。许可证 Apache-2.0。

Chrome / Edge browser DOM support is implemented and covered by automated/local fixture tests.
Manual Chrome / Edge GUI validation: **Skipped before release by explicit user decision.** Real-world feedback remains recommended after release; no claim that all real websites were manually verified.

## Still not supported

- 填空题、简答题完整求解。
- 自动点击、勾选、提交或下一题。
- OCR、原生 Anthropic API。
- 所有网页 100% DOM 兼容或模型答案 100% 准确。

Canvas、图片题、复杂 iframe、封闭 Shadow DOM 和特殊控件可能回退 Vision。配对仅本次有效，重启后重配。配对连接中断且无法确认原标签时取消，避免截取别的页面。

这是正式 **v0.2.0 Release**，不是 Pre-release。历史 v0.1.0rc1 保留原标签与 Pre-release 状态。
