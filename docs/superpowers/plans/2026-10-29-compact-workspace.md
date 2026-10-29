# Compact Workspace Implementation Plan

> **For agentic workers:** Use the scoped native and frontend agents; root integrates and verifies.

**Goal:** 小方框展开答案、明暗主题、精简界面与含 EXE 的首选下载入口。

**Architecture:** 保留本机同源 API 和 WebView2，用自有原生窗口模式配合响应式前端；更新与捕获生命周期保持隔离。

**Tech Stack:** Python / Win32 / pywebview、HTML/CSS/JS、Playwright。

**Spec:** [设计](../specs/2026-10-29-compact-workspace-design.md)

## Global Constraints

- AQ 约 80×80；展开仅显示答案与思路，保留全部复制操作。
- 不新增模型请求、截图保存、自动点击或提交；不读取私人屏幕验收。
- 仅界面主题保存到非秘密偏好；关闭仍退出并释放 F8/ESC。
- Windows 0.6.0，Android 0.5.0 独立下载，发布保持 Pre-release。

## Review Focus

- 浮窗不能出现在实际截图中；排除失败不能覆盖题目或切错前台。
- 收起/恢复、重复启动、拖动与退出不能遗留窗口或线程。
- 窄窗、深色与长答案必须可滚动、可读、可选中复制。
- 设置/配对/更新仍可访问，工作台不残留离线 Demo 邀请。
- 新用户主按钮下载 EXE 包，不能误链源码或不存在的 Android 0.6 包。

## Tasks

- [x] Native agent：先测试窗口模式、同源鉴权和捕获排除，再实现 desktop_window/desktop_app/web_ui 集成；用自有合成窗口实测。
- [x] Frontend agent：先测试 80 方框、主题持久、窄窗与精简布局，再改 index/style/app；真实浏览器截图和复制验证。
- [x] Root：用失败测试固定 Android 独立版本链接，更新 README、下载页、版本和发布说明，保留首屏定稿介绍。
- [x] Review：跨端检查后运行 pytest、unittest、compileall、pip check、发布审计及可执行窗口验证。旧浏览器可见 smoke 的前台归属失败如实记录。
- [ ] Release：构建 Windows EXE ZIP，校验后更新原 GitHub 描述/README/Pages/Pre-release，验证下载与更新源，再更新桌面入口。
