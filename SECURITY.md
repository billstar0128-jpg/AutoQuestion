# Security policy

本机网页控制台使用仅 loopback 的随机端口与本次随机会话令牌。API 校验 Host 和令牌，写请求额外要求同源 Origin、JSON 格式及大小限制；无 CORS 放行或远程登录。资源采用严格 CSP；题目/模型文本按纯文本渲染。Key 仍由 Windows 凭据管理器或进程内存保存，不回传已保存值。有效本机用户隔离不能替代操作系统对恶意本机进程的防护。详见 [网页工作台边界](docs/WEB_UI.md#本机服务边界)。

当前版本为 0.2.2，提供 Windows x64 便携 App；历史发布标签保持不变。请使用已启用的 [GitHub 私密漏洞报告](https://github.com/billstar0128-jpg/AutoQuestion/security/advisories/new)。

0.2.0 新增扩展与本机 bridge 信任边界：Origin / Host / 路径检查、内存配对码、Windows TCP 所有者与进程匹配、消息大小和协议校验。只有本次授权的扩展会话能响应取题；网站不能直接调用桥接提取。不要分享配对码；可关闭程序/断开扩展撤销会话。localhost 不等于所有本地软件可信，已控制当前用户或浏览器的恶意软件不在此隔离能力范围内。

API Key 暴露、凭据处理缺陷、意外截图、意外 DOM 访问、任意文件访问、代码执行风险和日志泄密都属于安全问题。发现后先停止受影响流程，记录版本、复现步骤和经过脱敏的错误类别，通过上述私密渠道报告；不要把漏洞利用中的秘密放进 public issue。

不要上传真实 Key、Credential dump、私人截图、学校/账户信息或原始敏感日志。Doctor 输出不包含 Key 值，但包含解释器路径；复制到 Bug Report 前自行检查并删去用户名等个人路径。

若 Key 曾进入 Git history：**REVOKE / ROTATE THE CREDENTIAL**。仅删除当前文件不够，公开 push 前还必须清理 Git history，并再次审查提交、分支、标签和历史。忽略规则不能消除已跟踪文件或历史。

普通设置保存在用户 AppData，Key 使用 Windows Credential Manager 或仅本次内存；向导不会写明文 Key 文件。环境变量及显式 `--env-file` 是用户主动管理的高级方式，不能提交这些真实配置。

发布前必须完成 [Release Checklist](docs/RELEASE_CHECKLIST.md)。保护范围及局限见 [Security Model](docs/SECURITY_MODEL.md)，数据流见 [Privacy](PRIVACY.md)。未知第三方 Provider、网关和依赖具有各自的信任边界；安全检查不是没有漏洞的保证。
