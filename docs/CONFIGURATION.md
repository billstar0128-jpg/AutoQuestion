# Advanced Configuration / Troubleshooting

普通用户先按 [README](../README.md) 使用向导。优先级：process environment > explicit `--env-file` > AppData config > defaults。程序不会自动寻找 `.env`，文件不做变量插值，向导不修改环境变量。

| Variable | Default / constraint |
|---|---|
| HOTKEY / EXIT_KEY | F8 / ESC；支持 ESC、F1～F11，不能相同 |
| DEBOUNCE_MS | 400；300～500 |
| INPUT_MODE | vision 兼容默认；auto / dom / vision / demo |
| IMAGE_MAX_EDGE | 2048；1024～4096，不放大小图 |
| LLM_PROVIDER | fake / openai；默认 fake |
| LLM_API_KEY | 真实 API 必需，仅在本机安全提供 |
| LLM_BASE_URL | HTTP(S) API root，禁止凭据、query、fragment；不要填到 chat/completions |
| LLM_MODEL | 账户可调用的 model identifier |
| LLM_SUPPORTS_VISION | false；确实支持图片的模型才设 true |
| LLM_TIMEOUT_SECONDS | 30；1～120 有限秒数 |
| AUTO_ACTION | 旧模板预留，当前不读取、不执行动作 |

显式文件用 `main.py --env-file .env` 加载；[模板](../.env.example) 的 Key 保持空白。完整显式配置可跳过向导，仅 HOTKEY 等辅助变量不会跳过。Config 默认 fake/vision 是兼容行为，API 向导推荐 AUTO。

## Offline examples

```powershell
$env:INPUT_MODE = 'demo'
$env:LLM_PROVIDER = 'fake'
.\.venv-win\Scripts\python.exe main.py
```

以上固定 MANUAL 首都题无需浏览器。离线四题 DOM 先安装 Chromium，再将 INPUT_MODE 改为 dom，启动相同命令。AUTO DOM 路由测试用 auto 和 `main.py --open-demo`。Fake 遇到 Canvas/外部窗口会在截图前提示 Vision 不可用。测试后用新的终端避免环境变量覆盖保存设置。

## Secure configuration

`%APPDATA%\AutoQuestion\config.json` 的 config_version=1，仅保存 profile、protocol、显示名、地址、model、能力、模式、timeout、尺寸和非秘密凭据引用，不含 api_key。只有一个活动配置；多个保留旧 Key 不等于多 Profile 管理界面。

Windows Credential Manager 使用当前用户的 Generic Credential，本地持久保存。替换为 copy-on-write：新安全凭据 → 临时非秘密 JSON → flush/fsync → 原子 replace；失败回收本次新引用，旧 Key 保留。切换 Provider 或 session-only 不自动删除旧 Key。多个旧引用无法确定账户时重新询问 Key。强制结束/断电可能留下未引用安全凭据，reset 可明确清理。

Windows console 输入支持粘贴、退格、Enter、Ctrl+C，显示星号；其他可隐藏终端用 getpass。无法安全隐藏则拒绝输入，不从非交互管道读取 Key。凭据后端不可用时选 Session-only / Retry / Cancel，不降级到明文文件。Python 内存秘密副本不保证完全擦除。

`--setup` 可 Keep / Replace / session-only / switch offline。`--reset-config` 先确认删除普通配置，再询问删除所有本项目凭据，后者默认 No。保存前取消不写配置；保存后的可选 Demo 提问时取消，已经确认保存的配置仍保留。session-only 下次只询问 Key，不重跑完整向导。

损坏 JSON 或未知版本/profile/protocol 可重设、仅本次忽略并用 Offline、或退出；完整显式配置可运行并保留损坏文件。错误不回显原始内容。

## Diagnostics

Base URL 填 API 根地址（例如 `https://api.deepseek.com`），Model ID 填模型标识（`<your-current-model-id>` 对应的实际值）。不要把两者交换。Setup 会立即拒绝填在 Base URL 中的 Model ID，或填在 Model ID 中的 URL，只重问出错字段。此检查完全离线，不验证模型是否存在或 Key 是否有效。旧配置疑似输反时会提示重新运行 `--setup`，不会静默交换。

show-config 展示公开字段和凭据状态，不调用 get；URL 含 query secret、用户信息或 fragment 时固定报错，不回显输入。Doctor 不读 Key 值，只检查变量名/凭据元数据，因此不能证明 Key 有效；它不读 --env-file，即使显式传入也提示忽略。

Doctor 的 PASS/WARNINGS 退出 0，FAIL 退出 1。Chromium probe 是隔离可回收的 headless 检查；当前 Doctor 检查完整开发环境，即使普通 AUTO 不需要浏览器，缺 runtime 也会报告 FAIL。只需普通 AUTO/Vision 的用户可继续使用已配置模型；需要完整 Doctor 通过或 Demo 时安装 runtime。安装与运行的 PLAYWRIGHT_BROWSERS_PATH 必须一致，默认 0，升级 Playwright 后重新安装配套 Chromium。

| Problem | Action |
|---|---|
| AUTO 没弹 Demo | 正常，需要 DOM 测试时加 --open-demo |
| --open-demo 被拒绝 | 检查有效模式是否 demo，或是否混用了管理 CLI |
| 没有向导 / 配置未生效 | 检查保存值与环境优先级，用 --setup / --show-config |
| Fake / Vision disabled | 使用 DOM/offline 或确实支持图片的模型 |
| Canvas 导航停顿 | 退出旧实例再 --open-demo；空闲导航应完成，无需 F8 解卡 |
| 热键注册失败 | 关闭旧实例及占用 F8/ESC 的应用 |
| API / JSON 错误 | 在本地或服务商账户排查，错误后 READY，不追加 Vision |
| 目标移动/切换/关闭 | 重新把题目置前台后 F8 |
| 可见 smoke 焦点失败 | 在交互终端重跑，测试窗口保持前台，不放宽身份保护 |

详见 [Privacy](../PRIVACY.md) 和 [Manual Acceptance](MANUAL_ACCEPTANCE_M13.md)。
