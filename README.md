# AutoQuestion

**题目在屏幕上，F8 一按，答案出来。**

最开始它只是我为了省掉“截图 → 上传 → 问模型”这一串重复操作写的小工具，后来慢慢补上了 Vision、DOM、AUTO 路由、多选/判断题、首次配置向导和安全的 API Key 存储。

现在它可以常驻在 Windows 后台。你把 WPS、PDF、记事本或其他题目窗口放到前台，按 F8，它会调用你自己配置的模型分析当前题目；处理完以后回到 READY，等下一题。

支持 DeepSeek、Kimi、GLM、OpenAI 和自定义 OpenAI-compatible API。没有自己的服务器，没有遥测，也不会替你点击或提交答案。

**0.1.0rc1 还是第一个公开 Release Candidate。** 如果你愿意测试，遇到难装、难懂、识别失败或者任何反直觉的地方，Issue 比“能跑”更有价值。

## What it does

用于自建题库、本地 Demo、非计分练习、调查问卷和获得授权的学习场景。模型可能答错，结构校验不能代替人工核对。

- 常驻 F8 / ESC，支持 BUSY 和 debounce，每次只分析一道题。
- 支持单选、多选、判断，保留无字母选项的实际文本。
- 前台窗口 Vision、受管理本地 Demo DOM、AUTO 路由和无 Key 的 Offline Demo。
- 首次设置向导、Provider Profiles、Windows Credential Manager、session-only Key 和本地 Doctor。
- 不会自动选择、点击、提交或翻到下一题。

## Quick Start

准备标准 **Windows CPython**，不要使用 MSYS2/MinGW Python。最低语法和依赖目标是 Python 3.10；当前本机实际验证 **CPython 3.14.6**，3.10 / 3.12 / 3.14 的 Windows CI 已配置，但尚未在线运行。其他环境尚不能视为已验证支持。

从 [GitHub 仓库](https://github.com/billstar0128-jpg/AutoQuestion) 取得完整源码，在项目根目录打开 PowerShell。

```powershell
git clone https://github.com/billstar0128-jpg/AutoQuestion.git
cd AutoQuestion
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-win\Scripts\python.exe main.py
```

无需激活虚拟环境。普通 AUTO、Vision 和固定 Offline Demo 不需要安装 Chromium runtime；本地 DOM Demo 才需要，见下节。

### First-run Setup

没有有效保存配置或完整显式配置时，程序进入向导。以 DeepSeek 为例：选择 Provider → 确认 API root → 填账户可调用的 Model ID → 确认这个模型的图片能力 → 选择 AUTO → 安全输入 Key → 选择 Windows Credential Manager 或 session-only → 确认保存。

Base URL 是 API 根地址，例如 `https://api.deepseek.com`；Model ID 是服务商提供的模型标识，填写 `<your-current-model-id>` 对应的实际值。填反时向导会立即拒绝并重问当前字段，保留之前填好的信息。校验完全离线，不请求模型列表、不验证 Key。

项目不绑定 DeepSeek，也可选择 Kimi、GLM、OpenAI 或 Custom。模型名称不预填未经验证的永久值；**只有确实支持图片输入的模型才能完成外部窗口/Canvas Vision 分析**。文本模型可选择 DOM，或接受向导的能力警告；不要只因为品牌名就启用 Vision。

AUTO / Vision 保存后询问 `Open the local demo quiz now? [y/N]`：直接 Enter 不打开浏览器，进入 READY；Yes 只在本次打开 Demo。DOM 模式按其定义自动打开 Demo，不再重复询问。Offline Demo 不询问 Key，也不打开浏览器。

Key 输入显示星号或完全隐藏。普通配置写入 `%APPDATA%\AutoQuestion\config.json`，Key 不进入 JSON；默认安全保存在当前 Windows 用户的 Credential Manager。session-only 下次只再询问 Key。第二次普通启动直接加载配置、进入 READY；AUTO 不弹 Demo、不重跑完整向导。

进入 READY 后，将自己授权的 WPS、记事本、PDF 或其他题目窗口置于前台，按 F8，等恢复 READY 再分析下一题。真实请求发送到你配置的 Provider，可能产生其 API 费用。ESC / Ctrl+C 会停止接受任务并清理；已有同步请求需等完成或超时。

## Try the Local Demo

四题 Demo 包括带字母单选、无字母单选、多选、判断；另有 Canvas 行星题。它是测试和可选教程，不是程序的必经主界面。

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
.\.venv-win\Scripts\python.exe -m playwright install chromium
.\.venv-win\Scripts\python.exe main.py --open-demo
```

以上启动沿用有效配置。AUTO 下将 Demo 置前台按 F8，普通题显示 `Input: DOM`；手动点击“打开 Canvas 测试题”，画布应完整显示，F8 显示 `DOM unavailable → Fallback: VISION`；返回普通题后再次 F8 恢复 DOM。Canvas 需要支持图片的真实模型，Fake 不支持 Vision。ESC 关闭本次 Chromium 并释放线程/热键。

无 Key 用户优先在 Setup 选择 **Offline Demo**，F8 回答固定 MANUAL 首都题，无 Chromium、无截图、无 API。若要离线体验四道 DOM 题，可按 [高级配置](docs/CONFIGURATION.md) 临时设置 fake/dom；这些演示答案的 99% 是固定值，不是模型准确率。

## How F8 Works: AUTO / DOM / Vision

| 有效 INPUT_MODE | 普通启动 | 加 `--open-demo` |
|---|---|---|
| auto | 不创建浏览器，READY；没有受管理 DOM 时使用 Vision | 打开本地 Demo；前台匹配后 DOM 优先，取题失败才回退 |
| dom | 自动打开受管理 Demo，只用 DOM，不回退 | 与普通 DOM 启动相同 |
| vision | 不打开浏览器，只用前台窗口 Vision | 打开 Demo 供视觉测试，仍不读 DOM |
| demo | 固定 MANUAL 文本示例，无浏览器 | 明确拒绝组合 |

`--open-demo` 不修改永久 INPUT_MODE，也不与 `--setup`、`--doctor`、`--show-config`、`--reset-config`、`--version` 混用。需要重设时用 `--setup` 并在向导末尾选择本次 Demo。

AUTO 的 DOM 只限 **AutoQuestion 管理的本地 Demo Browser**。普通 WPS、PDF、记事本和个人浏览器内容使用 Vision；不会读取任意个人浏览器 DOM、扫描 Chrome tabs 或接管个人 profile。AUTO 并不代表 DOM-read every website。

DOM 成功不截图。获取题目失败才 fallback；已得到题目后的认证、网络、模型 JSON 或答案错误直接 ERROR → READY，不再追加图片请求。目标窗口切换、移动或关闭会取消捕获，不能改截其他窗口。详见 [Architecture](docs/ARCHITECTURE.md)。

## Supported Providers

Profile 是厂商预设，Protocol Provider 是实际请求适配器。

| Profile | Protocol | 建议 API root |
|---|---|---|
| DeepSeek | OpenAI-compatible | `https://api.deepseek.com` |
| Kimi / Moonshot | OpenAI-compatible | `https://api.moonshot.cn/v1` |
| Zhipu / GLM | OpenAI-compatible | `https://open.bigmodel.cn/api/paas/v4/` |
| OpenAI / GPT | OpenAI-compatible | `https://api.openai.com/v1` |
| Custom OpenAI-compatible | OpenAI-compatible | 用户填写 |
| Offline Demo | Fake | 不使用 API |

已有 API root 核对依据保留：[DeepSeek](https://api-docs.deepseek.com/)、[Kimi](https://platform.kimi.com/docs/get-api-key)、[智谱](https://docs.bigmodel.cn/cn/guide/develop/openai/introduction)。真实预设可编辑地址和模型；预设可用不等于厂商所有模型都经过本项目验证。Vision 是具体 Model 的配置能力，不是品牌永久属性。

Native Anthropic / Claude API **not supported in 0.1.0rc1**。通过兼容网关调用 Claude 可以尝试 Custom，但不保证所有网关兼容。ChatGPT Plus / Pro 订阅不等于 OpenAI API Key 或 API billing balance，登录 ChatGPT App 不会自动提供 API 凭据；参见 [OpenAI API Quick Start](https://developers.openai.com/api/docs/quickstart)。

## Supported Question Types / limitations

完整回答协议支持 `single_choice`、`multiple_choice`、`true_false`。无字母选项不会生成 A/B/C/D。填空和简答只预留 Schema，尚未完整支持求解。

不支持 OCR、原生 Anthropic、任意个人 Chrome DOM 接管、浏览器扩展、自动点击/勾选/提交/下一题。没有 Web UI、数据库、遥测或云账户。不宣称支持所有网站、所有 AI 模型或 100% accurate。0.1.0rc1 以完整 Python 源码目录为目标，不提供 EXE/MSI、PyPI 或独立 wheel 分发。

## Privacy and Security

DOM 向所选 Provider 发送结构化题干和选项；Vision 发送 F8 目标窗口的可见区域图片。通知、覆盖层和标题栏也可能进入图片，请只显示你希望发送的内容。没有开发者 telemetry、analytics、crash upload、中央服务器或截图历史。

Key 不进入普通 config、日志、repr 或仓库。不要上传真实 `.env`、配置、凭据导出或私人截图。若 Key 曾进入 Git history，必须撤销/轮换并清理历史，删除当前文件不够。见 [PRIVACY](PRIVACY.md)、[SECURITY](SECURITY.md)、[Security Model](docs/SECURITY_MODEL.md)。

## Configuration / Doctor

```powershell
.\.venv-win\Scripts\python.exe main.py --setup
.\.venv-win\Scripts\python.exe main.py --show-config
.\.venv-win\Scripts\python.exe main.py --doctor
.\.venv-win\Scripts\python.exe main.py --version
# 需要重置时才运行；凭据清理会另行确认，默认 No。
.\.venv-win\Scripts\python.exe main.py --reset-config
```

环境变量和显式 `--env-file` 仍可使用，优先级为 process environment > explicit file > AppData > defaults；主路径优先使用向导。详见 [Advanced Configuration / Troubleshooting](docs/CONFIGURATION.md)。Doctor 不调用 Provider、不读真实 Key 值、不截图、不注册热键；Chromium 检查仅运行隔离可回收的 headless 探针。报告前检查其中个人解释器路径。

## Development / Contributing

运行依赖为 pydantic、openai、mss、Pillow、python-dotenv、playwright；pytest 只在开发依赖中。安装 `requirements-dev.txt` 和 Chromium 后顺序执行：

```powershell
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-win\Scripts\python.exe -m compileall -q main.py src tests
.\.venv-win\Scripts\python.exe -m pip check
.\.venv-win\Scripts\python.exe tools/release_audit.py
```

物理桌面另测 `.\.venv-win\Scripts\python.exe -X utf8 tests/smoke_browser_window.py -v`。关闭旧实例，测试窗口需获得前台；测试不会夺取其他用户窗口或读取真实屏幕像素。CI 不运行此可见 smoke；本地完整测试默认保留原生热键测试。

[Development](docs/DEVELOPMENT.md) · [Technical Notes](docs/TECHNICAL_NOTES.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Release Notes Draft](docs/RELEASE_NOTES_0.1.0rc1.md)

## License / publication state

AutoQuestion 使用 **Apache License 2.0（Apache-2.0）**，完整条款见 [LICENSE](LICENSE)。

**0.1.0rc1 · Public Release Candidate · Pre-release，非 Stable。**

[问题反馈](https://github.com/billstar0128-jpg/AutoQuestion/issues) · [Actions](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/ci.yml) · [安全报告](https://github.com/billstar0128-jpg/AutoQuestion/security/advisories/new)

测试步骤见 [Windows 人工验收](docs/MANUAL_ACCEPTANCE_M13.md)，发布进度与验证结果见 [Release Checklist](docs/RELEASE_CHECKLIST.md) 和 [M14 验证记录](docs/VALIDATION_M14.md)。正式 0.1.0 Stable 尚未发布。
