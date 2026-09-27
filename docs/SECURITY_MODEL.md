# Security model

## Assets and trust boundaries

保护 API Key、窗口图像、结构化题目、浏览器隐私和用户配置。Windows 用户会话、Python 解释器、依赖、用户选择的 Provider 都是信任边界。项目不尝试防御已控制电脑的恶意管理员、完全失陷的 Windows Session、恶意 Python interpreter 或恶意 Provider。

## Controls

- Key 不进入普通 JSON、日志或对象 repr。Windows 原生安全存储只允许 `AutoQuestion/<profile>/<reference>` 命名空间；session-only 不落盘。
- Setup 输入遮罩/隐藏，无法安全隐藏则拒绝输入；确认保存前不写配置、不启动热键/浏览器。配置与凭据分开写，失败尽量回滚新引用。
- 窗口目标在 F8 时固定；PID/HWND/边界变化取消捕获，拒绝全屏兜底。32M 原始像素、最长边限制和 8 MiB PNG 上限控制内存。
- DOM 不读 Cookie、LocalStorage、SessionStorage、输入值、认证头或 whole HTML。只在自有 Demo 或已配对且授权站点的扩展会话执行只读语义提取。
- 本地 Demo 阻止外部请求、下载和 service worker。普通 Chrome/Edge 用 MV3 扩展，不接管个人 profile 或个人调试端口。
- Bridge 仅绑定 127.0.0.1，拒绝网页 Origin、错误 Host/路径、无配对码/错误协议、超大或畸形消息。配对码只在内存，用常量时间比较，不进入 URL、日志、配置或系统凭据。
- TCP tuple 的真实 PID/映像/创建时间与 F8 目标核对；浏览器内另核对 focused window、active tab 和 epoch，不信任客户端自报浏览器名。目标变化取消；配对浏览器截图前后确认原标签。
- 扩展默认不获全站读取权；activeTab 与用户选择的站点权限控制注入。无后台页面扫描、cookies/history/storage/tabs/debugger 权限，也无网页 externally_connectable 入口。
- Provider 的原始异常、响应体、请求头和 transport debug 日志不透出；协议校验失败不给伪造修正答案。
- 页面/图片里的指令被当作题目数据；程序没有执行模型返回命令、点击、文件访问或提交动作的通道。

## Limits

结构一致性不是知识准确率或 prompt injection 的完美防御。图像可能含可见覆盖层与标题栏。第三方 Provider 收到用户请求后如何处理数据不由本项目控制。OS 强制结束或断电可能留下未引用安全凭据，Python 内存秘密副本不保证全部擦除；显式 reset 可清理本应用旧凭据。

Doctor 调用 Windows 枚举接口只访问名称/类型，立即释放返回结构，不解码 CredentialBlob；这不意味着操作系统接口内部从未接触凭据。Secret audit 是有限模式检查与候选文件人工审查，不证明任意秘密不存在，更不能清除 Git history。

依赖由用户主动通过 pip/Playwright 下载，本项目不 vendor 第三方源码或浏览器 runtime。发布前复核依赖许可、历史和候选文件，见 [Release Checklist](RELEASE_CHECKLIST.md)、[Security](../SECURITY.md)。
