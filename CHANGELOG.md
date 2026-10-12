# Changelog

## Unreleased

### Added

- 本机网页工作台：配置模型、启动／停止、查看真实题目与答案、内存记录和扩展配对。
- AutoQuestion.pyw 双击入口及图形化首次依赖准备，日常使用不需要 PowerShell。
- DeepSeek / Kimi / GLM / OpenAI 的 URL、Model ID 与图片能力示例；网页与控制台向导共用，不自动选择模型或启用图片。
- GitHub Pages 静态 UI 交互预览；禁用 API Key 输入，不读取屏幕或调用模型。

### Security / Privacy

- 本机控制台使用随机端口、会话令牌、Host / Origin 校验与严格 CSP；安全凭据和既有 F8 路由复用原实现。
- 已保存 Key 不回传浏览器，截图不落盘，题目记录只在内存中保留，退出清空。
- v0.2.0 标签与正式 Release 保持原样，新增界面通过 main 源码获取。

## 0.2.0

### Added

- Browser DOM support for normal Chrome / Edge pages through an optional MV3 extension.
- Localhost Browser Bridge, memory-only pairing and foreground target classification.
- DOM → Vision fallback, synthetic fixtures, bridge/extension/router tests and installation documentation.

### Changed

- AUTO prefers DOM for supported browser pages; desktop applications use Vision directly.
- Strict DOM uses the foreground target; --open-demo explicitly opens the managed Playwright Demo.
- Existing config_version=1 settings and API credentials remain compatible; websockets 15 is the only new runtime dependency.

### Security / Privacy

- F8-triggered DOM access, localhost-only bridge, minimal permissions and per-site grants.
- No cookie/password/input-value/history collection or personal browser profile takeover.
- Native process matching and browser window/tab checks; provider errors never trigger an extra image request.

### Limitations

- Canvas/image-heavy pages, complex iframe/Shadow DOM and ambiguous controls may fall back to Vision.
- fill_blank / short_answer remain unsupported; no automatic clicking, submission or next question.
- Chrome / Edge support is implemented and covered by automated/local fixture tests. Real GUI acceptance was skipped before release by explicit user decision and remains a non-blocking follow-up.

## 0.1.0rc1 — Public Release Candidate (Pre-release)

### Added

- Windows 常驻 F8 分析、ESC 退出、BUSY 和 debounce。
- single_choice、multiple_choice、true_false 的 DOM/Text/Vision 协议与答案一致性校验。
- First-run Setup、六个 Provider Profile、Windows Credential Manager 和 session-only Key。
- Doctor、配置管理命令、发布审查工具、用户/维护文档及已通过的 Windows CI 工作流。

### Changed

- Setup 的 Base URL / Model ID 在当前字段立即离线校验；旧配置及合并后的配置复用相同规则，疑似输反时提示重新填写。
- AUTO 普通启动直接 READY，不再强制打开四题 Chromium Demo。
- `--open-demo` 和向导完成后的默认 No 选择，只影响本次浏览器启动。
- DOM 仍自动打开本地 Demo；Vision 显式打开 Demo 时仍只走 Vision。
- 版本从开发标记调整为发布候选；运行入口仍是 `python main.py`。

### Security

- 保留窗口身份保护、只读 DOM、acquisition-only fallback、无截图落盘和安全错误信息。
- 非秘密 AppData 配置与凭据分离；源码发布候选排除私人配置、日志、截图、环境及旧实验文件。
- 使用 [Apache License 2.0](LICENSE)；安全问题可通过 GitHub 私密漏洞报告提交。

### Known limitations

- 仅 Windows；本机验证 CPython 3.14.6，Windows GitHub CI 验证 3.10.11 / 3.12.10 / 3.14.7；其他环境未经验证。
- DOM 只支持项目受管理 Demo；不读取任意个人浏览器 DOM。
- Fake 只支持内置题，不支持 Vision；模型准确性与各厂商兼容性需人工验证。
- 不完整支持填空/简答，不支持原生 Anthropic、OCR 或任何自动作答动作。
