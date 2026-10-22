# 0.3.0 验证记录

本次修改覆盖同屏多题、Windows 答案展示和 Android 悬浮识题。测试使用合成题目和模拟响应，不调用用户的付费 API，也不抓取私人屏幕。

2026-10-22，Windows CPython 3.14.6 本机结果：

- pytest：306 passed，431 subtests passed，58.78 秒。
- unittest：306 tests，OK，61.240 秒。
- compileall、pip check、Doctor、release_audit 通过。
- 单图单请求返回多个答案、三到六道混合单选/多选/判断、无字母判断答案、多选规范排序、任一题矛盾时整批拒绝、停止后不发布答案均已覆盖。
- 真实 headless Chromium 验证受管理 DOM、已发布扩展提取器、本机 bridge 的多题流程；六题逐题答案保持对应，控件始终未勾选。工作台六题可同时查看，390×844 手机练习页没有裁切题干或选项。
- 使用最终打包依赖另跑 5 个 Vision batch unittest，通过。
- Windows 原生 EXE 在中文及空格临时路径、PATH 只有 System32 的环境，通过首配安全凭据、Fake/F8、重复进程复用窗口、右上角关闭后 GUI/HTTP 退出和 F8/ESC 释放；exit 0。无真实 API 或私人截图。
- 可见窗口 smoke 已执行，但当前会话 GetForegroundWindow 返回 0，无法满足测试的前台 HWND 条件；未通过，不计为已验收。headless DOM/Canvas 往返和原生 EXE 生命周期另有通过结果。

Android 结果：

- JDK 17、SDK 36、AGP 8.13 / Gradle 8.13 实际编译 debug、release APK；15 项 JVM 协议/配置测试通过。
- Android Lint：0 errors、1 warning（测试用 org.json 存在更新版本提示，非运行时依赖）。实际修复了旧 API Insets、返回手势和资源版本边界问题。
- Android 16 / API 36 独立模拟器的 instrumentation：1 test，OK，5.168 秒。真实系统整屏共享授权 → 42dp 悬浮按钮 → 真实内存 PNG，严格验证截图包含合成题目的青色背景 → 六道单选/多选/判断分别展示 → 同一授权会话旋转并再次读屏 → 停止释放 projection → 新授权后停止正在进行的请求，均通过。网络由测试 APK 内存替身接管，不请求真实 Provider。
- 重复 BUSY 点击不追加请求，停止取消当前请求，App files/cache 和共享 DCIM/Pictures 没有图片文件。
- 真捕获测试曾发现不可变 Bitmap 擦除失败，已改成可修改的 Bitmap 并重新通过真实读屏；截图不落盘。
- 发布 APK 使用独立本机私钥签名，签名验证通过，未设置 debuggable，不含 instrumentation 类或测试网络替身，内含未经修改的 Apache-2.0 LICENSE。应用不申请相册、媒体、存储、无障碍权限，无第三方运行时库。
- APK SHA-256：`82bfa9fc36ab15f05aa7f873f0f6d40075f4ae76ed1f5ef9a0dd1948714c79f9`。

未连接用户手机，不能据此宣称已通过小米真机验收。模型真实视觉能力、知识答案、不同 HyperOS 权限/后台策略仍需用自己的配置和授权练习页面核对。本次作为 Pre-release 提供安装测试。
