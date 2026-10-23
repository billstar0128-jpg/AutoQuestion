# 0.4.0 验证记录

本轮覆盖主观题、与客观题的同屏混合、两端选择和复制答案。测试使用合成题目和模拟响应，不抓取用户私人屏幕或调用付费模型。Android 仅在自建模拟器验证，不代表用户小米真机验收。

2026-10-23，Windows CPython 3.14.6 本机结果：

- pytest：331 passed、484 subtests passed，90.25 秒。
- unittest：331 tests，OK，81.636 秒。
- compileall、pip check、Doctor、release_audit 和 diff 检查通过。
- 单图单请求返回六道混合题，覆盖单选、多选、判断、两空填空、数学解答和多段简答；文本 SDK MockTransport、图像 SDK MockTransport 与严格协议校验通过。填空数量、字段混用或任一答案矛盾时整批拒绝，停止后不发布迟到结果。
- 真实 headless Chromium 覆盖受管理 DOM、扩展、Bridge 和 AUTO：保留主观题多段材料，不读取作答框内容；必要题图、Canvas 等使 DOM 获取失败并回退 Vision。Provider 或答案错误仍不回退。原 DOM / Canvas / DOM 往返和客观题回归通过。
- 工作台在 headless Chromium 中实际验证整段解答、逐空及整题复制、剪贴板与 Ctrl+V 粘贴保留换行；界面轮询不会打断文字选择。模型文本按纯文本显示，概览缩略不截断详情或复制内容。两份六题练习页在 390×844 视口完整可见。
- 打包依赖环境另跑 6 项主观题 unittest，通过。Windows EXE 在中文及空格临时路径、PATH 只有 System32 的环境，通过首次配置安全凭据保存、Fake/F8、重复进程复用窗口、标题栏关闭后 GUI/HTTP 退出和 F8/ESC 释放；exit 0。
- 可见窗口 smoke 已执行，但当前会话不满足测试自己的前台 HWND/PID 条件，未通过，不计为已验收；没有强行接管其他前台程序。headless 浏览器回归和原生 EXE 生命周期另有通过结果。
- 原生 WebView2 另测了真实按钮点击和自建文本框 Ctrl+V，但当前工具桌面会话中 OpenClipboard 持续返回 Windows 错误 5（访问被拒绝），剪贴板序号不变，未完成原生跨应用粘贴确证，不能计为通过。未增加绕过限制的剪贴板桥接或读取代码。请在正常桌面启动 App 后，复制填空/解答并在记事本粘贴验收；headless 前端复制测试与 Android 原生复制测试的通过结果不替代这项验收。

Android 结果：

- JDK 17、SDK 36、AGP 8.13 / Gradle 8.13 实际构建 debug、test 和正式签名 release APK；23 项 JVM 协议/配置测试通过。
- Android Lint：0 errors、1 warning（测试用 org.json 新版本提示，不是运行时依赖）。
- Android 16 / API 36 模拟器 instrumentation：1 test，OK，11.583 秒。真实系统共享授权、内存 PNG 和合成画面像素验证、六道混合题独立显示、客观题复制、填空逐空/整题复制、数学及多段简答复制均通过。
- 真实触摸长按弹出原生 Copy 菜单，选择多行子串；每条复制路径验证敏感剪贴板标记，并通过 EditText 实际粘贴核对完整文字、公式与换行。
- 忙碌时不追加请求、同一授权会话旋转后再识题、停止释放共享与悬浮窗、新授权后停止取消请求、files/cache/DCIM/Pictures 无截图文件，均通过。
- 发布包复用原签名，已实际从原 0.3.0 覆盖升级至 0.4.0 并冷启动。Release 不含 debug 测试宿主、instrumentation、模拟网络或测试凭据，没有 debuggable、媒体/存储/无障碍权限，LICENSE 与根文件字节一致，不含签名私钥。
- APK SHA-256：`46c78858591f8d27b92de4cde8cdc17c98945bc2d21be718db153b5db3fac74d`。

未连接用户手机；这些结果不代表小米 / HyperOS 真机或真实模型的答案效果已通过验收。主观题结构校验不能证明答案正确。复制后的文本由系统剪贴板管理，停止 App 不会清除它。本版作为 Pre-release 提供安装测试。
