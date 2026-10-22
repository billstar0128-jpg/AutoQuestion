# Android 悬浮答题

Android 版使用原生界面，在手机上直接配置模型，通过一个 **42dp 的 AQ 小方框**读取当前屏幕。支持同屏最多 10 道完整、清晰可读的单选、多选、判断题，按屏幕阅读顺序分别给出题干、答案、简短理由和置信度。不会点击、勾选或提交答案。

这是首个 Android 测试版本 **0.3.0**，要求 Android 8.0（API 26）或更新版本。安装包不依赖电脑运行，也不需要 AutoQuestion 的服务器。当前未连接用户的小米手机；构建和自动检查不能代替 HyperOS 真机验收。

## 安装与第一次配置

1. 从项目 [GitHub Releases](https://github.com/billstar0128-jpg/AutoQuestion/releases) 下载 `AutoQuestion-0.3.0-Android.apk`，在手机上打开 APK，按系统提示允许这次安装。以后更新请使用同一项目发布的安装包。
2. 打开 AutoQuestion。选择 DeepSeek 或 OpenAI 示例，检查 URL 和 model，填写该服务商的 API Key，点“保存配置”。
3. 点“开启悬浮识题”，允许系统的“显示在其他应用上层”，返回应用后再次点击开启。
4. 系统会询问屏幕共享授权。应用默认请求共享整个屏幕，以便在不同应用之间切换；部分系统仍可能提供区域选择，此时需要切换多个应用就选“整个屏幕”。如果只共享一个应用，其他应用的内容不会被读取。
5. 允许通知后，可在常驻通知中随时点“停止”。通知不是题目历史，不显示题目、答案或 Key。

保存配置后，API Key 输入框会清空；留空再次保存会保留已存 Key。更换到不同服务器必须重新填写对应 Key，以免把旧服务的 Key 发到新地址。手机与 Windows 的配置分别保存在各自设备，不会自动同步。

## 可直接照填的示例

| 服务 | Base URL | Model 示例 | 手机截屏 |
| --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com` | `deepseek-flash` | 官方文档目前支持图片 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4.1-mini` | 支持图片 |
| 自定义 | 服务商提供的 HTTPS OpenAI-compatible Base URL | 服务商公布的、支持 `image_url` 的 model ID | 取决于模型和接口 |

Base URL 不要带 `/chat/completions`，程序会自动补上。不要把服务商的聊天网站地址当作 API 地址。

示例依据 2026-10-22 的 [DeepSeek 图片输入文档](https://api-docs.deepseek.com/guides/vision/)、[DeepSeek 模型列表](https://api-docs.deepseek.com/api/list-models/)和 [OpenAI 图片输入文档](https://developers.openai.com/api/docs/guides/images-vision)。`deepseek-v4-pro` 在当前官方列表中为文本模型，不适用于手机截屏识题；不能仅凭名字中有 DeepSeek 就认为支持图片。服务商未来可能调整模型，请以其当前文档和账户权限为准。

手机应用直接向你填写的地址发送 HTTPS Chat Completions 请求，不经过项目作者的服务器。API 服务的计费、可用地区和数据留存规则由服务商决定。

## 小方框怎么用

- **轻点 AQ**：读取当前屏幕的一张图片，一次请求分别回答这一屏的完整题目。处理时显示 `···`，不会叠加并发请求。
- 单选、多选、判断题可以混在同一屏，3、4、5、6 道题也会分别处理，最多 10 道。题多时模型可能需要更久，读取超时设为 180 秒；可随时停止。
- **拖动 AQ**：移动小方框；初始位置在左上方。识题时会先移除本应用的浮窗，再从新画面读取图片，避免答案面板挡住题目。
- **长按 AQ**：查看本次会话最近一屏的答案，或点“停止”。答案面板可以收起。
- **按 Home**：继续保留已授权的悬浮服务，以便切换到题目应用。
- **停止并退出 / 通知里的停止 / 划除最近任务**：结束屏幕共享、网络任务和悬浮窗，清空会话答案。不会自动开机启动，也不会自动重启屏幕共享。

系统结束共享、锁屏后共享失效或服务被系统终止时，需要回到应用重新开启并授权。Android 的屏幕共享授权不能永久跳过。应用使用一个授权会话和一个 VirtualDisplay；旋转时调整现有显示与 Surface，不重复使用一次性授权令牌。

## 图片和 Key 保存在哪里

- 截图只存在于 `ImageReader`、Bitmap、PNG 和请求内存中，**不写相册、不写截图文件**，应用不申请照片、媒体或存储权限。
- 只有你轻点识题时才会编码并向所填 API 发送一张图片。屏幕共享开启期间，系统仍会提供屏幕帧；未触发识题的帧会立即释放，不会上传。
- API Key 使用 Android Keystore 中不可导出的 AES 密钥进行 AES-GCM 加密，应用私有配置只保存密文与公开 URL/model。禁用应用备份，不把 Key 写入日志或通知。
- 网络只允许 HTTPS，不跟随重定向，防止认证信息被转发到其他地址。错误提示不展示服务商原始响应。
- 题目、答案仅保留在当前会话内存，停止后清除。Java 的字符串和操作系统/网络库缓冲区不能保证逐字节即时擦除；“不保存截图”不等于服务商不会留存收到的图片。

## 小米 / HyperOS 验收

不同 HyperOS 版本的权限名称可能不同。请在系统的 AutoQuestion 应用权限页面允许显示悬浮窗，按系统提示授权屏幕共享；如果悬浮窗被系统阻止，可检查系统提供的悬浮窗或后台弹出界面权限。只有实际遇到后台被终止时，再检查该应用的省电限制。应用不要求 root、无障碍服务、设备管理员或相册权限。

建议先打开一张含完整单选和多选的普通练习页面，确认：

1. AQ 只占一个小方框，可拖到左上角。
2. 轻点后显示两道独立题目及各自答案，未把选项串题。
3. 收起答案、切换应用后仍可再次识题；横竖屏切换后可继续使用。
4. 进入相册，没有生成截图；拒绝/撤回共享后不再识题。
5. 点停止、返回退出或划除任务后，AQ 和共享状态消失，再次开启需要新的系统授权。
6. 无效 Key、无网络、文本模型、受保护页面分别显示可理解的错误，不自动重试或保存图片。

银行、密码、DRM 或主动禁止截屏的页面可能得到黑屏；应用不会绕过 Android 的保护。题目太小、反光、裁切或选项不完整会影响识别。自动检查只能验证协议和代码，不能保证模型答案正确。

## 本版已经做过的自动验证

2026-10-22，在 Android 16 / API 36 模拟器中实际安装并运行：系统屏幕共享授权、小方框触发真实 MediaProjection 画面、内存 PNG 请求、六道混合单选/多选/判断题的独立答案面板、忙碌时重复点击不排队、横竖屏调整、停止释放授权与浮窗、停止时取消正在进行的请求，以及应用文件/缓存和公共 DCIM/Pictures 没有截图文件。端到端 instrumentation 测试通过。

这项测试使用程序生成的公开练习画面，并在内存中替换 HTTPS 返回六道合成答案；没有发送真实模型请求，也没有采集用户私人屏幕。另有 15 项 JVM 单元测试验证多题顺序、3～6 道混合题、串题/索引/标签错误整批拒绝、严格 JSON 和 HTTPS/Key 配置边界，全部通过。Android Lint 无错误，剩余一条仅提示测试用 `org.json` 存在更新版本。小米 / HyperOS 真机权限和实际服务商模型效果仍需按上面的步骤验收。

## 源码构建

源码在 [`android/`](../android/)，使用 Java 17、Android SDK 36、Android Gradle Plugin 8.13 和 Gradle 8.13；运行时无第三方依赖。项目根目录的 [`tools/build_android_app.ps1`](../tools/build_android_app.ps1) 提供 Windows 构建入口，生成 APK；本地 SDK、Gradle 缓存、签名密钥及 APK 不提交到 Git。

安装好 JDK 17、SDK platform 36 和 build-tools 35.0.0 后，可在 PowerShell 运行 `./tools/build_android_app.ps1`。默认执行 debug 编译、15 项协议/配置单元测试和 Android Lint；正式签名包使用 `./tools/build_android_app.ps1 -Release`。构建脚本会校验下载的 Gradle 8.13 SHA-256，APK 输出到 `dist/`。Android CI 同样执行 debug 编译、单元测试和 lint，不读取私有发布签名。

发布签名通过 `ANDROID_KEYSTORE_FILE`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` 环境变量配置。签名密钥必须私下保存，后续可安装更新必须使用同一把密钥。不要将密钥、密码、`local.properties` 或设备配置提交到公开仓库。

Windows 构建脚本在未提供签名环境变量时，第一次 `-Release` 会在 `%LOCALAPPDATA%\AutoQuestionAndroidSigning\` 创建并复用私有发布密钥，密码用当前 Windows 用户的 DPAPI 保护。请做好私下备份；DPAPI 密码备份绑定当前 Windows 用户环境，迁移开发设备时要先按你自己的安全方式迁移签名凭据，不要直接生成一把新密钥覆盖已有公开版本。

实现依据 Android 官方的 [MediaProjection 授权、前台服务和旋转说明](https://developer.android.com/media/grow/media-projection)、[应用悬浮窗口 API](https://developer.android.com/reference/android/view/WindowManager.LayoutParams#TYPE_APPLICATION_OVERLAY) 和 [Android Keystore](https://developer.android.com/privacy-and-security/keystore)。
