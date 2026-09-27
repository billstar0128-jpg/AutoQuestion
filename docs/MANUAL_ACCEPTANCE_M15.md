# M15 Windows Chrome / Edge acceptance — 0.2.0

这些步骤保留为发布后的 NON-BLOCKING MANUAL FOLLOW-UP。
Skipped before release by explicit user decision.
自动 Chromium 测试不是 Chrome / Edge 人工验收，也不证明真实模型准确率；本轮不等待这些步骤，不阻断提交或正式发布。

先按 [扩展安装](BROWSER_DOM_SETUP.md) 完成安装、配对与 localhost 示例服务器；关闭其他 AutoQuestion。
使用 AUTO 与确实支持图片的模型，API Key 仅在本机设置。未配真实模型时可先 fake/dom 测结构化题，再单独补 Vision 验收。

1. Chrome 加载原始 extension，输入本次配对码并允许 localhost 站点；确认 connected，关两个弹窗后 READY。
2. single_choice / multiple_choice / true_false / no_labels 分别 F8：Input: Browser DOM、答案、READY；无 CAPTURING、选项未被勾选。
3. noise_page 不带入密码/文本输入值或隐藏题；spa_like 手动换题后 F8 读取新题；iframe_question 读取同源题。
4. canvas_question F8：Browser DOM unavailable → Fallback: VISION → 答案 → READY。返回普通页恢复 Browser DOM。
5. Chrome → WPS 或记事本题目窗口 → Chrome：中间为 Input: VISION (desktop target)，无 DOM attempt；返回恢复 Browser DOM。
6. 在 Chrome 禁用扩展，再 F8 普通题：AUTO 明确 unavailable 后 Vision。重新启用、配对后恢复。
7. Edge 独立安装原始 extension 并配对，重复步骤 2–6。
8. Chrome、Edge 同时打开不同合成题，交替放前台 F8，答案与当前页面一致。开两个浏览器窗口和多个标签再检查。
9. F8 后立即切换窗口/标签或关闭目标：取消、ERROR → READY，不读取新窗口/标签。保持稳定后再次 F8 可恢复。
10. INPUT_MODE=dom：WPS 明确报错不截图；Chrome/Edge 可用；未授权页报错不 fallback。INPUT_MODE=vision：不使用扩展 DOM。
11. AUTO 启动 `main.py --open-demo`，完成旧四题、Canvas、返回 DOM；仍显示 Input: DOM，个人浏览器不受影响。
12. 实际 Provider 认证或 JSON 错误后不追加 Vision；BUSY / debounce 无排队；ESC / Ctrl+C 清理，重启三次正常。已有同步 Provider 请求可能等待完成或超时。
13. --show-config / --doctor 没有 API Key 或配对码；普通 config 没有配对码字段；项目无新增截图或凭据文件。

请反馈 Chrome、Edge 各自的通过/失败项和脱敏状态文本，不发送 Key、配对码、私人截图或完整配置。
可见旧窗口 smoke 另在前台终端运行：

```powershell
.\.venv-win\Scripts\python.exe -X utf8 tests/smoke_browser_window.py -v
```

本轮发布只以自动测试、审计、真实 GitHub CI、新克隆安装及远端审计作为强制关卡。人工步骤不再阻断 **v0.2.0 Stable** 源码 Release。
