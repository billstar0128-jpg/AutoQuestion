# Windows M13 Manual Release Candidate Acceptance

只使用自己授权的内容，在项目根目录的 Windows Terminal / PowerShell 操作。关闭旧 AutoQuestion，开没有遗留 LLM_/INPUT_MODE 覆盖项的新终端。真实模型调用可能产生费用；只在本机输入 Key，不上传私人截图或配置。

## A. Automated tests

先按 [Development](DEVELOPMENT.md) 安装 requirements-dev 和 Chromium，再顺序运行 pytest、unittest、compileall、pip check、tools/release_audit.py，以及独立可见 smoke。核对 PASS / FAIL / SKIP 数量；本地全量不要设置 AUTOQUESTION_CI。可见 smoke 需测试窗口在前台，若被系统拒绝激活，在交互终端重跑；不得放宽窗口身份规则。

## B. Version

运行 ` .\.venv-win\Scripts\python.exe main.py --version`，应为 AutoQuestion 0.1.0rc1，不是 stable。

## C. Doctor

运行 `.\.venv-win\Scripts\python.exe main.py --doctor`。已安装全部依赖和 Chromium、真实配置完整时应 PASS；无 Key 的 Offline 状态可 WARNINGS。不能出现 Key、CredentialBlob、私人窗口标题。输出可能含个人解释器路径，分享前脱敏。它不验证模型或 Key 真伪。

## D. Normal DeepSeek AUTO startup

已有 M12 配置可直接运行 `.\.venv-win\Scripts\python.exe main.py`。需要首次流程时用 --setup，选择 DeepSeek（或其他 Profile）、账户可用 Model ID、真实图片能力、AUTO、安全输入及保存。图片能力按模型实际情况选择，不因品牌默认认为支持。

保存后对 Open local demo now? 直接 Enter。应 Provider / Model / Vision / AUTO → READY，**不得弹 Demo**。任务管理器中不应出现本次 AutoQuestion 创建的 Chromium/Playwright driver。保存配置已有有效 Key 时不应再次输入。

若是仅文本模型，先验证 DOM；外部窗口/Canvas Vision 验收需换用确实支持图片的模型，不能把设置 true 当作模型能力证明。

## E. WPS / external Vision

在 WPS 或记事本写一题：法国首都？A. 巴黎 B. 伦敦 C. 柏林 D. 罗马。只保留希望发送的内容，题目窗口置前台并保持不动，按 F8。预期 DOM unavailable → Fallback: VISION → CAPTURING → ANALYZING → 答案 → READY。不要读取任何后台 Demo。模型回答需人工核对，置信度不要求 99%。

## F. Explicit local Demo

ESC 退出后运行 `.\.venv-win\Scripts\python.exe main.py --open-demo`。应只开一个受管理 Demo。永久 INPUT_MODE 不变。管理命令加 --open-demo 应明确用法错误；固定 INPUT_MODE=demo 加该标志应拒绝，不创建两套 Demo。

## G. DOM single choice

将受管理 Chromium 放前台，保持一个窗口和标签，点页面空白处再 F8。首都题显示 Input: DOM，答案应 A；手动下一题，最大行星应显示木星，不生成字母。不出现 CAPTURING 或第二次 API 请求，不勾选任何控件。

## H. Canvas fallback and return

READY 空闲时点击“打开 Canvas 测试题”，不按 F8 解卡。应完整显示行星题和木星、地球、火星、金星四项。F8 后 DOM unavailable → Fallback: VISION；返回 DOM 测试题后 F8 恢复 Input: DOM。再测 Browser → WPS → Browser，原目标保持身份保护；不读取后台题。

## I. Multiple choice

手动到编程语言题，F8 应输出 Python、C、Java（真实模型答案需核对）。不自动勾选，不变成单选，不人为添加字母。另在自己的清晰文档中准备多选题，通过 Vision 复核协议。

## J. True-false

手动到“地球绕太阳公转。”，F8 应输出正确，保持原始选项文本。另通过 Vision 检查判断题。仍不勾选、不提交。

## K. BUSY / debounce / identity

请求中反复 F8 应 BUSY，不排队，不重复发送。长按只一次，快速双击受 debounce/BUSY 保护。触发后切换、移动或关闭目标，应取消/报错并恢复 READY，不能改截其他窗口。Provider 认证或 JSON 错误不得再 fallback 请求图片。

## L. ESC / Ctrl+C / cleanup

分别在普通 AUTO 和 --open-demo 下 ESC：停止接收任务，显示 STOPPED；本次 Chromium、driver、browser thread、worker 和热键释放。已有同步 API 请求可能需要等完成/超时。再启动退出三次；另外测 Ctrl+C，不残留本次进程，不影响用户自己的浏览器。

## M. Second startup

普通 main.py 再启动：不完整 Setup、不重输持久 Key、不弹 Demo，直接 READY。Session-only 是例外，应只重新询问 Key。上一轮选择 Open demo Yes 不得让这轮自动打开。

## N. Show-config

运行 main.py --show-config。核对 Profile、Protocol、Base URL、Model、Vision、模式和 Credential state，无真实 Key。URL 带 query、用户信息或 fragment 时安全拒绝，不回显其中 Secret。

## O. Candidate secret audit

运行 `.\.venv-win\Scripts\python.exe tools/release_audit.py --list`。应 PASS，逐个检查候选路径。脚本只覆盖有限模式，人工还要审查个人数据、测试 fixture 和 attribution；不要复制真实 .env 进入审查工具或公开输出。

## P. Public JSON contains no Key

只在本机检查 %APPDATA%\AutoQuestion\config.json，应无 api_key 字段或 Key 明文，只含非秘密配置与引用。不要把文件发到 issue。确认项目目录未生成普通 Key 文件、credential export 或截图。

## Q. Credential persistence

安全保存后 ESC，再启动应复用 Key。--setup 中 Keep 不需要输入 Key；取消保存不改变旧值。另测 session-only 下次只问 Key。系统凭据持久化与终端粘贴遮罩须人工验证，Mock 测试不能替代。需要清理时才运行 --reset-config，第二次“删除所有本项目凭据”确认默认 No；不要误删常用配置。

## R. Clean-room install

运行 `.\.venv-win\Scripts\python.exe tools/clean_room.py`，需要下载依赖/Chromium。检查新目录位于项目外，新 venv 与临时 APPDATA，脚本 PASS。无真实 Provider 调用或凭据写入。保留输出目录用于复核，勿误删开发目录。它是源码副本验证；如没有本地 commit，local git clone 仍为 N/A。

## S. Stranger Quick Start

按 [README](../README.md) 从完整源码、新 Windows CPython 和新环境重走安装。Offline Demo 选第 6 项，无 Key、无浏览器，F8 返回 A。真实配置测试按 D；同时验证保存后 Yes 能开 Demo、Enter 不开。文档不得要求开发者固定路径或隐含未包含文件。

## T. Local Git status

存在本地 Git 时运行 git status --short、git remote，确认候选仅为源码、测试、Demo、公开文档与配置模板；无 remote 时不添加。有远端也不得 push。未跟踪文件逐一审查，不使用盲目的 git add .。

## U. Staged-file / history audit

若尚未 staging，记录“未暂存”；未来提交前检查 git diff --cached --stat 和 git diff --cached，不应含真实 .env、环境、日志、截图、私人文件或 legacy_main.py。已有提交还需审查历史；Key 曾入历史必须 revoke/rotate 并清理后再公开。空暂存区不是历史安全证明。

## V. License gate

许可证已由用户确定为 Apache-2.0。确认根目录 [LICENSE](../LICENSE) 为标准完整文本，README 与 metadata 一致；正式再分发前复核 attribution 和再分发条件。

## W. Release checklist

逐项完成 [Release Checklist](RELEASE_CHECKLIST.md)，尤其真实 Provider、遮罩、Credential persistence、WPS Vision、完整清理。阅读 [Validation](VALIDATION_M13.md) 的自动/人工/未执行边界。不得把 CI 本地模拟写成 GitHub CI PASS。

## X. User publication decision

本轮 PUBLIC PUSH NOT PERFORMED。许可证已确定；只有用户完成人工验收并另行批准后，未来任务才可创建真实 GitHub 仓库/remote、最后审查 staging/history、push、等待 GitHub Actions、决定 stable/tag/Release。此步骤只记录用户本人决定，不自动执行。
