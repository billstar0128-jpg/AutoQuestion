# Contributing

当前为 0.1.0rc1 公开候选，使用 [Apache License 2.0](LICENSE)。请在 [Issues](https://github.com/billstar0128-jpg/AutoQuestion/issues) 报告问题，在 [仓库](https://github.com/billstar0128-jpg/AutoQuestion) 提交 PR；安全问题使用私密报告渠道。先阅读 [README](README.md)、[Architecture](docs/ARCHITECTURE.md) 与 [Development](docs/DEVELOPMENT.md)。

在项目根目录，用标准 Windows CPython 创建 `.venv-win`，安装 `requirements-dev.txt`，再设置 `PLAYWRIGHT_BROWSERS_PATH=0` 并安装 Playwright Chromium。完整命令和测试分类见 [Development](docs/DEVELOPMENT.md)。PR 前顺序运行 pytest、unittest、compileall、pip check 和 release audit；本机有交互桌面时另外运行可见窗口 smoke。

`src/autoquestion` 是应用，`tests` 只使用本地 HTML、合成图片、MockTransport 与 Fake Credential backend，`examples` 是人工导航的 Demo，`tools` 是本地发布审查工具。生产代码不操作答案控件。

增加同协议 Provider Profile：修改 `provider_presets.py` 注册表，核实官方 API root，补预设/覆盖/能力测试与文档。不要把品牌视为图片能力保证。新增协议适配器需要实现 `BaseLLMProvider`、安全错误转换、客户端释放与协议测试，不能只添加一个预设名称。

测试应验证行为和边界，不逐字锁死 README 文案。Provider 测试使用内存 transport，凭据测试使用注入的模拟后端；不要调用真实付费 API、操作真实凭据库或用未知第三方站点作默认 fixture。

禁止提交真实 Key、`.env`、AppData 配置、Credential export、截图和私人文档。提交前检查候选文件及 staged diff。漏洞报告遵循 [SECURITY](SECURITY.md)；Bug Report 的 Doctor 输出要先检查个人路径。M13 已冻结范围，不把自动点击、提交、翻题、OCR 或新题型夹带进维护 PR。
