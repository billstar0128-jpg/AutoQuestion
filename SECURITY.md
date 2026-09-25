# Security policy

0.1.0rc1 是公开 Release Candidate，尚未作为 stable 发布。请使用已启用的 [GitHub 私密漏洞报告](https://github.com/billstar0128-jpg/AutoQuestion/security/advisories/new)。

API Key 暴露、凭据处理缺陷、意外截图、意外 DOM 访问、任意文件访问、代码执行风险和日志泄密都属于安全问题。发现后先停止受影响流程，记录版本、复现步骤和经过脱敏的错误类别，通过上述私密渠道报告；不要把漏洞利用中的秘密放进 public issue。

不要上传真实 Key、Credential dump、私人截图、学校/账户信息或原始敏感日志。Doctor 输出不包含 Key 值，但包含解释器路径；复制到 Bug Report 前自行检查并删去用户名等个人路径。

若 Key 曾进入 Git history：**REVOKE / ROTATE THE CREDENTIAL**。仅删除当前文件不够，公开 push 前还必须清理 Git history，并再次审查提交、分支、标签和历史。忽略规则不能消除已跟踪文件或历史。

普通设置保存在用户 AppData，Key 使用 Windows Credential Manager 或仅本次内存；向导不会写明文 Key 文件。环境变量及显式 `--env-file` 是用户主动管理的高级方式，不能提交这些真实配置。

发布前必须完成 [Release Checklist](docs/RELEASE_CHECKLIST.md)。保护范围及局限见 [Security Model](docs/SECURITY_MODEL.md)，数据流见 [Privacy](PRIVACY.md)。未知第三方 Provider、网关和依赖具有各自的信任边界；安全检查不是没有漏洞的保证。
