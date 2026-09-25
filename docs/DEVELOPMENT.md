# Development

在完整源码根目录使用标准 Windows CPython。最低目标 3.10，本机实测 3.14.6；CI 的 3.10/3.12/3.14 matrix 尚未在线执行，不能宣传全部已验证。

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
.\.venv-win\Scripts\python.exe -m playwright install chromium
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-win\Scripts\python.exe -m compileall -q main.py src tests
.\.venv-win\Scripts\python.exe -m pip check
.\.venv-win\Scripts\python.exe tools/release_audit.py
.\.venv-win\Scripts\python.exe main.py --doctor
.\.venv-win\Scripts\python.exe main.py --version
```

完整测试顺序运行，避免热键冲突。默认保留真实注册/注销和 WM_HOTKEY 消息测试，不发送物理按键。可见桌面另测：

```powershell
.\.venv-win\Scripts\python.exe -X utf8 tests/smoke_browser_window.py -v
```

这是 **Local Windows Manual Smoke Test**，要求交互桌面和真实 HWND/PID/焦点，仅使用自建窗口、合成像素和 Mock Provider。窗口激活失败时安全停止，应在交互终端重跑，不扩大窗口操作范围。

## CI classification

AUTOQUESTION_CI=1 显式跳过 5 个交互桌面测试：Entrypoint 1、NativeHotkey 2、Reliability native lifecycle 1、Doctor held-hotkey 1。其余单元测试、Mock Win32 Credential ABI、真实 headless Chromium、配置、secret、Router 和 Startup UX 都运行。可见 smoke 不进入 CI，无 WPS、物理 F8、真实 API 或真实凭据写入。

本机全量回归不要设置此变量。模拟 CI 时设置后运行相同 pytest/unittest，完成后移除。工作流使用临时 APPDATA、只读权限、不需要 API Secret、不上传 artifacts。CI workflow prepared locally. It has not yet run on GitHub Actions.

## Clean-room

```powershell
.\.venv-win\Scripts\python.exe tools/clean_room.py
```

先审查候选源码，然后复制到项目外的新临时目录，创建全新 venv；不复制现有环境、AppData、Key 或浏览器状态。子进程只保留 Windows 启动所需环境，APPDATA/LOCALAPPDATA/USERPROFILE 指向临时目录，pip isolated 安装、Chromium 安装到新环境。验证 README 安装路径、版本、Doctor、模拟首次 Setup/Offline 和测试。目录保留并打印位置，供人工审查。

真实 Key 输入和系统凭据持久化仍需 [人工验收](MANUAL_ACCEPTANCE_M13.md)。无本地 commit 时不能声称 local clone PASS；独立源码副本 clean-room 不是 git clone。其余提交条件满足后再按 checklist 做无网络本地 clone。

## Version and dependencies

运行版本唯一来源：src/autoquestion/__init__.py 的 __version__。CLI/banner 导入，pyproject 通过 setuptools dynamic attr 读取，依赖动态读 requirements.txt。独立环境 `pip install --no-deps -e .` 可验证 metadata；普通用户仍安装 requirements 并运行 main.py。

目前不支持独立 wheel / PyPI 分发：Demo、Doctor 需要完整源码布局。editable metadata 成功不代表独立 wheel 功能验证。许可证为 [Apache-2.0](../LICENSE)，源码见 [GitHub 仓库](https://github.com/billstar0128-jpg/AutoQuestion)。

| Runtime dependency | Usage |
|---|---|
| pydantic | Question / Answer / UserConfig validation |
| openai | OpenAI-compatible SDK |
| mss | 目标窗口矩形捕获 |
| Pillow | 内存缩放与 PNG |
| python-dotenv | 显式 env-file |
| playwright | 本地 DOM、隔离 Doctor probe |

pytest 仅为开发依赖；setuptools 仅为可选 metadata 构建后端。没有新增运行依赖或全面升级。依赖与浏览器不 vendor 进源码，各自保留许可证；正式再分发需复核。pip check 只验证依赖一致性，不是漏洞审计。

## Design history

- M1–M5：配置、热键、TaskRunner、统一 Schema、Fake 与真实 SDK 内存 MockTransport。
- M6：同步 snapshot + worker capture；DPI/DWM/负坐标、内存 PNG、前后身份检查。
- M7–M9：语义 DOM、专用线程、acquisition-only fallback。Canvas 曾因 READY 空闲时同步 Playwright 不泵事件挂起，改为常驻 asyncio，不靠 sleep 或放宽 route。
- M10：多选数组/判断题，先校验再按 Question.options 顺序规范化，不补字母或修正错误答案。
- M11：安全错误、资源释放、只读 Doctor 和轻量 secret scan。
- M12：Profile 与 protocol 分离、AppData 非秘密配置、copy-on-write 凭据、遮罩输入。
- M13：可选 Demo 生命周期、RC 文档、仓库卫生和 CI 准备，无核心能力扩展。

保留协议示例和实现细节见 [Technical Notes](TECHNICAL_NOTES.md)、[Architecture](ARCHITECTURE.md)。参考 [Windows RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)、[Playwright Python](https://playwright.dev/python/docs/library)、[Pydantic validators](https://docs.pydantic.dev/latest/concepts/validators/)。未复制这些官方文档全文或 vendor 第三方源码。
