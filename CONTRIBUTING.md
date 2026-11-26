# 贡献指南

AutoQuestion 的完整运行源码使用 [Apache License 2.0](LICENSE) 公开。问题和功能讨论可提交到 [GitHub Issues](https://github.com/billstar0128-jpg/AutoQuestion/issues)，修改可通过 Pull Request 提交。发现漏洞时请使用 [私密报告渠道](SECURITY.md)。

开始前请阅读 [README](README.md)、[技术架构](docs/ARCHITECTURE.md)与[开发文档](docs/DEVELOPMENT.md)。Windows 应用位于 `src/autoquestion`，Android 应用位于 `android`，浏览器扩展位于 `extension`。`examples` 包含供本地验证的合成题目。

提交前运行与改动有关的已有检查。可见桌面检查依赖交互 Windows 环境，Android 权限和覆盖安装需要对应的模拟器或真机。已有自动检查使用合成数据、Fake 和 Mock 接口，详见 [已有自动检查](docs/DEVELOPMENT.md#已有自动检查)。

同协议服务商的配置示例由 `provider_presets.py` 维护。核实 API 根地址、模型 ID 和具体模型的输入类型，说明所支持的协议范围。新增适配器要遵循 `BaseLLMProvider` 接口、安全错误映射和客户端资源释放约定。

请检查候选文件和暂存差异，署名以外的私人信息、真实 Key、`.env`、应用配置、凭据导出、私人截图和签名文件不应进入仓库。项目的输入与输出边界见 [隐私说明](PRIVACY.md)。
