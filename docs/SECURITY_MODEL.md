# Security model

## Assets and trust boundaries

保护 API Key、窗口图像、结构化题目、浏览器隐私和用户配置。Windows 用户会话、Python 解释器、依赖、用户选择的 Provider 都是信任边界。项目不尝试防御已控制电脑的恶意管理员、完全失陷的 Windows Session、恶意 Python interpreter 或恶意 Provider。

## Controls

- Key 不进入普通 JSON、日志或对象 repr。Windows 原生安全存储只允许 `AutoQuestion/<profile>/<reference>` 命名空间；session-only 不落盘。
- Setup 输入遮罩/隐藏，无法安全隐藏则拒绝输入；确认保存前不写配置、不启动热键/浏览器。配置与凭据分开写，失败尽量回滚新引用。
- 窗口目标在 F8 时固定；PID/HWND/边界变化取消捕获，拒绝全屏兜底。32M 原始像素、最长边限制和 8 MiB PNG 上限控制内存。
- DOM 不读 Cookie、LocalStorage、SessionStorage、password value、认证头或 whole HTML。仅在自有 Demo 会话执行只读语义提取。
- 本地 Demo 阻止外部页面请求，禁止下载和 service worker；没有个人 Chrome 接管、remote-debugging 用户连接或浏览器扩展。
- Provider 的原始异常、响应体、请求头和 transport debug 日志不透出；协议校验失败不给伪造修正答案。
- 页面/图片里的指令被当作题目数据；程序没有执行模型返回命令、点击、文件访问或提交动作的通道。

## Limits

结构一致性不是知识准确率或 prompt injection 的完美防御。图像可能含可见覆盖层与标题栏。第三方 Provider 收到用户请求后如何处理数据不由本项目控制。OS 强制结束或断电可能留下未引用安全凭据，Python 内存秘密副本不保证全部擦除；显式 reset 可清理本应用旧凭据。

Doctor 调用 Windows 枚举接口只访问名称/类型，立即释放返回结构，不解码 CredentialBlob；这不意味着操作系统接口内部从未接触凭据。Secret audit 是有限模式检查与候选文件人工审查，不证明任意秘密不存在，更不能清除 Git history。

依赖由用户主动通过 pip/Playwright 下载，本项目不 vendor 第三方源码或浏览器 runtime。发布前复核依赖许可、历史和候选文件，见 [Release Checklist](RELEASE_CHECKLIST.md)、[Security](../SECURITY.md)。
