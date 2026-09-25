# Changelog

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
