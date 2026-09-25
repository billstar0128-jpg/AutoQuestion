# Privacy

AutoQuestion 不运行开发者中央服务器，没有 telemetry、analytics、crash upload、更新信标、截图历史存储或自动上传浏览历史。按 F8 才启动一次分析，BUSY/debounce 不会排队追加分析。

| 路径 | 发给用户所选 Provider 的内容 |
|---|---|
| 固定 demo + Fake | 无网络请求，只回答内置精确匹配题 |
| demo + 真实 Provider | 固定 MANUAL 示例题的结构化文本 |
| DOM + 真实 Provider | 当前题干、选项、题型及来源 DOM 标识 |
| Vision / AUTO fallback | F8 目标窗口对应屏幕矩形的内存 PNG，以及图像分析协议 |

AUTO 默认不打开浏览器；普通 WPS、PDF、记事本和个人浏览器窗口通过 Vision 分析。只有显式打开的受管理本地 Demo 能走 AUTO DOM。不会扫描个人 Chrome tabs、接管浏览器 profile，或读取 Cookie、LocalStorage、SessionStorage、密码输入、认证头、整页 HTML。

窗口标题用于内存快照，不打印、不单独上传；但截图中的标题栏、个人信息、通知和覆盖层可能随图片发送。截图是可见屏幕区域，不是后台渲染；请将希望分析的题目完整置于前台。窗口失焦、移动、关闭或越界会取消本次捕获，不改截全屏。图片只在内存流转，第三方 Provider 对收到的数据有自己的保留与使用政策，用户需自行了解。

普通配置位于 `%APPDATA%\AutoQuestion\config.json`，包含 Provider、模型、地址、能力和凭据引用，不含 Key。Windows Credential Manager 由当前 Windows 用户保存 Key；session-only Key 只用于当前进程，退出后不由程序持久化。Python 内存无法保证所有秘密副本都被可靠擦除，不宣称防御系统内存取证。

控制台显示题干、答案与状态；终端自己的日志、屏幕录制和复制操作不受 AutoQuestion 管理。`--show-config` 显示非秘密配置；URL 中的用户信息、查询参数和片段被验证拒绝，避免 query secret 回显。Doctor 只读取凭据元数据，不解码 CredentialBlob。

配置重置使用 `main.py --reset-config`；删除所有本项目凭据需要另行确认，默认保留。详见 [Advanced Configuration](docs/CONFIGURATION.md) 和 [Security](SECURITY.md)。
