# Privacy

Windows App 的界面服务只监听 127.0.0.1 随机端口，在你点击启动并按 F8 后运行识题。API Key 输入仅发送给本机程序，不进入浏览器持久存储；已保存的 Key 不回传。最多 20 条题目/答案记录保留在进程内存，主动清空或退出时销毁。关闭 App 原生窗口会停止服务、释放热键并退出。公开 GitHub Pages 是下载入口与静态预览，预览禁用 Key 输入，无法读取屏幕或调用模型。详见 [App 使用说明](docs/WEB_UI.md)。

Android App 由用户授权悬浮窗和 MediaProjection 屏幕共享。只有点击悬浮按钮才把一帧画面用于识题请求，截图不写入文件、不写入相册，也不请求相册或存储权限。共享会话期间 Android 会持续向内存 Surface 投影，非触发帧立即丢弃；停止服务后释放投影、Surface、悬浮窗和网络任务。Key 由 Android Keystore 的 AES-GCM 密钥加密保存，本地备份关闭，不返回给网页。图片直接发送给用户设置的 HTTPS Provider；屏幕上的个人信息也可能包含在图片中。手机锁屏、系统停止共享或主动停止后需重新授权。详见 [Android 使用说明](docs/ANDROID.md)。

两端只在用户点击复制或执行文字选择菜单的复制动作时，把所选答案写入系统剪贴板，不读取原有剪贴板、不自动粘贴到其他应用。Android 的答案复制标记为敏感内容，以减少系统预览。主动复制之后，操作系统剪贴板、剪贴板历史或目标应用可能继续保留这些文字；清空记录、停止或退出本 App 不会清空系统剪贴板，也不能删除已粘贴到其他应用的文字。

AutoQuestion 不运行开发者中央服务器，没有 telemetry、analytics、crash upload、截图历史存储或自动上传浏览历史。按 F8 或点击手机悬浮按钮才启动一次分析，BUSY/debounce 不会排队追加分析。同屏多题 Vision 使用一次图片请求，DOM 分别发送各题文本。

0.5.0 起，两端在启动、返回前台和前台运行期间每 15 分钟检查本项目的公开 GitHub Releases，也可手动检查。GitHub 会接收正常 HTTPS 请求信息（例如 IP 和程序版本 User-Agent）；更新请求不附带 API Key、模型配置、题目、答案、截图或本机会话令牌，也不联系开发者自建更新服务器。离线 Demo 的题目不调用模型，但自动更新检查仍会访问 GitHub。只有主动点击下载才获取安装包，校验 SHA-256 后由用户确认安装；不静默安装、不自动卸载旧版。Windows 保留旧版本目录和原配置；Android 安装包暂存私有缓存，由只读临时 URI 交给系统安装器，不进入相册。安装器需要用户允许安装此来源的应用。断网或 GitHub 限流不会阻止原有答题。

| 路径 | 发给用户所选 Provider 的内容 |
|---|---|
| 固定 demo + Fake | 无网络请求，只回答内置精确匹配题 |
| demo + 真实 Provider | 固定 MANUAL 示例题的结构化文本 |
| DOM + 真实 Provider | 当前题干、选项（主观题为空）、题型、填空数量及来源 DOM 标识，不含输入框已填值 |
| Vision / AUTO fallback | F8 目标窗口对应屏幕矩形的内存 PNG，以及图像分析协议 |

AUTO 默认不打开浏览器；WPS、PDF 阅读器、记事本和其他桌面进程直接 Vision。已配对的 Chrome / Edge 可通过可选扩展 DOM；显式打开的受管理 Demo 继续使用自有 Playwright 会话。不会接管个人浏览器 profile、连接个人调试端口，或读取 Cookie、LocalStorage、SessionStorage、密码/输入值、认证头、整页 HTML。

扩展只在 F8 请求时读取当前前台页面的可见题干、选项和题型，不后台轮询页面内容。浏览器焦点、标签激活和导航事件只更新内存中的 window/tab ID 与版本号；不收集浏览历史或发送 URL、标题。Windows 侧读取 F8 的进程可执行路径/创建时间及 localhost TCP 所有者，核对 Chrome/Edge 会话归属，不上传这些标识。

扩展经 `127.0.0.1:37841` 发送小型题目结果给 Python，再由 Python 按已有设置调用 Provider。此 bridge 只在本机监听，不是开发者服务器。配对码由每次启动随机生成，只在本地配对窗口显示，扩展仅内存保留；不进入 API Key 存储、普通 config、日志、URL 或仓库。扩展没有 storage/cookies/history 权限。按站点授予的浏览器权限由浏览器自身保存，可在扩展详情撤销。手动复制配对码可能进入系统剪贴板历史。

窗口标题用于内存快照，不打印、不单独上传；但截图中的标题栏、个人信息、通知和覆盖层可能随图片发送。截图是可见屏幕区域，不是后台渲染；请将希望分析的题目完整置于前台。窗口失焦、移动、关闭或越界会取消本次捕获，不改截全屏。图片只在内存流转，第三方 Provider 对收到的数据有自己的保留与使用政策，用户需自行了解。

普通配置位于 `%APPDATA%\AutoQuestion\config.json`，包含 Provider、模型、地址、能力和凭据引用，不含 Key。Windows Credential Manager 由当前 Windows 用户保存 Key；session-only Key 只用于当前进程，退出后不由程序持久化。Python 内存无法保证所有秘密副本都被可靠擦除，不宣称防御系统内存取证。

控制台显示题干、答案与状态；终端自己的日志、屏幕录制和复制操作不受 AutoQuestion 管理。`--show-config` 显示非秘密配置；URL 中的用户信息、查询参数和片段被验证拒绝，避免 query secret 回显。Doctor 只读取凭据元数据，不解码 CredentialBlob。

配置重置使用 `main.py --reset-config`；删除所有本项目凭据需要另行确认，默认保留。详见 [Advanced Configuration](docs/CONFIGURATION.md) 和 [Security](SECURITY.md)。

0.6.0 Windows 的主题选择写入独立的 `ui-preferences.json`，只包含非秘密显示偏好，不加入 Key/模型配置。小方框与展开窗口共用原有内存结果，点击 AQ 仅显示已取得的答案，不自动截屏或增加模型请求。为避免 App 遮挡题目，原生会话捕获时仅排除或短暂隐藏本进程的 App 窗口，捕获后恢复且不激活；不会为了避让而隐藏其他应用，也不额外读取与本次题目目标无关的窗口。
