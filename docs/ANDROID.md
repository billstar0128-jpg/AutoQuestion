# Android 使用指南

Android 版使用原生界面，在手机上直接配置模型，通过一个 **42dp 的 AQ 小方框**读取当前屏幕。支持同屏最多 10 道完整、清晰可读的单选、多选、判断、填空及主观简答/解答题，按屏幕阅读顺序分别给出题干、答案、简短理由和置信度。答案可长按选择或点击复制，由你自行切换应用粘贴；不会点击、勾选、自动填写或提交答案。

当前公开可下载的 Android 版本为 **0.6.1（GitHub Pre-release）**，适用 Android 8.0（API 26）及更新版本。可在手机上独立配置和使用。

**已装 0.5.0 时，打开 AutoQuestion 可自动检查 0.6.1。下载和安装都需你确认。0.4.0 及更早版本可直接下载新 APK 覆盖安装，以保留配置和 Key。**

## 安装与第一次配置

1. 下载 [AutoQuestion-0.6.1-Android.apk](https://github.com/billstar0128-jpg/AutoQuestion/releases/download/v0.6.1/AutoQuestion-0.6.1-Android.apk)，在手机上打开 APK，按系统提示确认安装。以后更新请使用同一项目发布的安装包。
2. 打开 AutoQuestion，填入支持图片输入的模型 ID、Base URL 和 API Key，再点“保存配置”。示例可以修改。参见 [API 配置指南](API_SETUP.md)。
3. 点“开启悬浮识题”，允许系统的“显示在其他应用上层”，返回应用后再次点击开启。
4. 切换到题目应用，轻点 AQ 并确认系统的屏幕共享提示。应用默认请求整个屏幕。若系统允许选择共享范围，可只共享题目所在的应用。需要边录屏边识题时，请先开启录屏兼容。
5. 允许通知后，可在常驻通知中随时点“停止”。通知不是题目历史，不显示题目、答案或 Key。

保存配置后，API Key 输入框会清空；留空再次保存会保留已存 Key。更换到不同服务器必须重新填写对应 Key，以免把旧服务的 Key 发到新地址。手机与 Windows 的配置分别保存在各自设备，不会自动同步。

## 应用内更新

从 0.5.0 起，首页的“应用更新”卡片会显示当前版本、检查状态和可安装的新版本。打开或回到应用时会检查原项目的公开 GitHub Releases；在首页保持前台时，每 15 分钟检查一次。短时间反复切换应用会合并检查，避免 GitHub 限流；“检查更新”按钮可手动重试。它包含 Pre-release 测试版，排除草稿，不使用会漏掉测试版的 `/releases/latest` 接口。

发现新版本后，由你点击下载。下载完成会验证大小、GitHub SHA-256 摘要、发布页附带的 `SHA256SUMS.txt`（如果存在）、包名、版本与当前 App 的签名。只有同包名、同签名且 `versionCode` 更高、版本名称也符合所选发布版本的 APK 才能安装；安装前还会再次校验缓存文件。校验失败会阻止安装，不会卸载现有应用。

点“安装已下载更新”后，应用会先停止悬浮识题，避免遮挡系统授权。若系统要求“允许此来源安装应用”，请自行决定是否授权，返回 AutoQuestion 后再次点安装；随后仍由 Android 的安装确认页面决定是否覆盖更新。拒绝授权或取消安装可以稍后重试，旧版本和已保存配置保持不变。应用不会静默安装，也不会代替你点击系统确认。

更新检查访问固定 GitHub 仓库的公开发布信息，模型配置和请求内容不会发给 GitHub。[隐私说明](../PRIVACY.md)。

检查与下载都由前台页面管理，退到其他应用时会停止正在进行的更新网络任务，后台 AQ 悬浮识题不会保持更新连接，也不新增常驻更新服务。检查失败只在卡片提示，识题仍可使用。APK 下载到应用私有缓存，不进入相册或公共下载目录；取消更新或普通退出会清理下载缓存。已经交给系统安装器的文件可能短暂保留，供安装器读取，之后由应用清理。

## 小方框怎么用

- **轻点 AQ**：读取当前屏幕的一张图片，再向模型发送请求。普通模式需要确认系统共享提示，取到画面后立即释放共享。处理时显示 `···`，重复点击不会发起新请求。
- 单选、多选、判断、填空及主观简答/解答题可以混在同一屏，3、4、5、6 道题也会分别处理，最多 10 道。题多时模型可能需要更久，读取超时设为 180 秒；可随时停止。
- **拖动 AQ**：移动小方框；初始位置在左上方。识题时会先移除本应用的浮窗，再从新画面读取图片，避免答案面板挡住题目。
- **长按 AQ**：查看本次会话最近一屏的答案，或点“停止”。答案面板可以收起。
- **按 Home**：继续保留已授权的悬浮服务，以便切换到题目应用。
- **停止并退出 / 通知里的停止 / 划除最近任务**：结束屏幕共享、网络任务和悬浮窗，清空会话答案。不会自动开机启动，也不会自动重启屏幕共享。

取消授权或系统中断本次共享后，可再点 AQ 重试。只有悬浮窗服务被终止时才需要回到应用重新开启。

## 系统截屏和录屏

AQ 待机、等待模型及显示答案时均不占用屏幕共享。在允许截屏的页面，可使用手机自带的截屏和录屏功能，可见的 AQ 按钮和答案也会被记录。设置页继续保护 API Key 的输入界面。

在 Android 11 及以上，可用录屏兼容功能录下识题和答案出现的过程：

1. 在 AutoQuestion 首页点“设置录屏兼容”，在系统无障碍服务列表里启用“AutoQuestion 录屏兼容”。返回首页时可查看连接状态。
2. 开启悬浮识题，打开题目，使用手机控制中心启动系统录屏。希望录下 AQ 和答案时，请选录制整个屏幕。
3. 轻点 AQ 识题。启用录屏兼容后，AQ 只请求一次系统截图，录屏继续运行。答案出现后，按手机原有方式停止录屏。

如果 Android 13 及以上安装的 APK 在无障碍设置中显示“受限设置”，从可信来源安装后可按系统说明设置。 [Android 受限设置说明](https://support.google.com/android/answer/12623953)

在 Android 8–10 或关闭录屏兼容时，AQ 使用普通共享流程。请在录屏结束后再确认共享，Android 可能在新共享开始时结束已有录屏。 [Android 屏幕共享说明](https://developer.android.com/media/grow/media-projection)

## 填空、简答和复制

填空题会识别实际空位数，按“第 1 空、第 2 空……”分别显示答案，每空都可以单独复制。也可以点“复制本题答案”，得到按空位顺序分行的完整内容。一道填空最多 20 空，每空答案最多 2000 字；空位数量与答案数量不一致时，不展示这一屏不一致的结果。

简答、计算、解答和论述题使用同一种主观题结果，保留完整答案的段落、换行和必要推导步骤，最多 12000 字。`short_reason` 只作简短说明，不会替代完整答案；纯文本公式按模型返回的内容显示，不把所有解题过程压成一行。

在答案面板中长按文字可以选择子串并复制；“复制本题答案”只复制完整答案，不夹带题干、理由或置信度。填空整题复制带空位编号，逐空复制则只有该空答案。复制后先收起面板，自行切换到目标应用，使用那个应用的粘贴操作。

主动选择复制后，文本可能留在系统剪贴板。Android 13 及以上标记复制内容为敏感，以减少系统预览。[Android 复制粘贴与敏感内容](https://developer.android.com/develop/ui/views/touch-and-input/copy-paste)。

## 隐私与剪贴板

0.6.1 使用截图识题。普通模式在屏幕共享后读取一帧，释放共享再向你配置的 HTTPS 模型服务发送图片。录屏兼容使用系统无障碍截图接口。该服务不订阅无障碍事件、不读取控件树，也不执行手势。截图只在内存中处理，应用不请求相册或存储权限。[Android 单帧截图接口](https://developer.android.com/reference/android/accessibilityservice/AccessibilityService#takeScreenshot(int,%20java.util.concurrent.Executor,%20android.accessibilityservice.AccessibilityService.TakeScreenshotCallback))

Key 加密存放在应用私有配置。停止悬浮识题会清除本次会话答案。主动复制的内容可能留在系统剪贴板，模型服务也有各自的数据留存政策。[隐私说明](../PRIVACY.md)

## 小米 HyperOS 权限

系统权限名称随 HyperOS 版本而变化。在 AutoQuestion 的应用权限页面允许显示悬浮窗，普通模式按系统提示授权屏幕共享。录屏兼容需要单独启用相应的系统无障碍服务。浮窗消失时可检查悬浮窗、后台弹出界面权限及该应用的省电设置。

先用普通练习页确认可移动 AQ、取消屏幕共享后可重试、旋转后可继续使用，并检查停止后浮窗是否消失。已有媒体投影与复制流程的模拟器验证使用合成题和模拟模型结果。不同 HyperOS 真机的权限行为需要实机确认。

银行、密码界面、受 DRM 保护或主动禁止截屏的页面可能显示黑屏。题目太小、选项出屏、图片不完整也会影响识别。[常见问题](FAQ.md)

## 源码构建

源码在 [`android/`](../android/)，使用 Java 17、Android SDK 36、Android Gradle Plugin 8.13 和 Gradle 8.13；运行时无第三方依赖。项目根目录的 [`tools/build_android_app.ps1`](../tools/build_android_app.ps1) 提供 Windows 构建入口，生成 APK；本地 SDK、Gradle 缓存、签名密钥及 APK 不提交到 Git。

安装好 JDK 17、SDK platform 36 和 build-tools 35.0.0 后，可在 PowerShell 运行 `./tools/build_android_app.ps1`。默认执行 debug 编译、协议/配置单元测试和 Android Lint；正式签名包使用 `./tools/build_android_app.ps1 -Release`。构建脚本会校验下载的 Gradle 8.13 SHA-256，APK 输出到 `dist/`。Android CI 同样执行 debug 编译、单元测试和 lint，不读取私有发布签名。

需要复现更新安装测试时，使用 `./tools/build_android_app.ps1 -UpdateTestFixtures` 另行生成一次性的同签名新版本、不同签名和不同包名 APK，并编译 instrumentation 测试。这些合成安装包只放在被 Git 忽略的 `build/` 目录，不是公开版本；安装测试应只在专用模拟器运行，不能安装到日常手机或使用真实 Key。此参数不会代替系统的安装确认步骤。

发布签名通过 `ANDROID_KEYSTORE_FILE`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` 环境变量配置。签名密钥必须私下保存，后续可安装更新必须使用同一把密钥。不要将密钥、密码、`local.properties` 或设备配置提交到公开仓库。

Windows 构建脚本在未提供签名环境变量时，第一次 `-Release` 会在 `%LOCALAPPDATA%\AutoQuestionAndroidSigning\` 创建并复用私有发布密钥，密码用当前 Windows 用户的 DPAPI 保护。请做好私下备份；DPAPI 密码备份绑定当前 Windows 用户环境，迁移开发设备时要先按你自己的安全方式迁移签名凭据，不要直接生成一把新密钥覆盖已有公开版本。

实现依据 Android 官方的 [MediaProjection 授权、前台服务和旋转说明](https://developer.android.com/media/grow/media-projection)、[应用悬浮窗口 API](https://developer.android.com/reference/android/view/WindowManager.LayoutParams#TYPE_APPLICATION_OVERLAY) 和 [Android Keystore](https://developer.android.com/privacy-and-security/keystore)。
