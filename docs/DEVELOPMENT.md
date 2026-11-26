# 开发与源码运行

Windows 版使用标准 **CPython 3.10 或更新版本**，请使用 Windows 原生 Python。只想使用应用时，可在 [README](../README.md) 下载 Windows 程序包。Android 源码构建见 [Android 指南](ANDROID.md#源码构建)。

## Windows 快速安装

在 PowerShell 中运行以下命令。第一行需要 Git。

```powershell
git clone https://github.com/billstar0128-jpg/AutoQuestion.git
cd AutoQuestion
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-win\Scripts\python.exe main.py
```

虚拟环境可直接调用，无需激活。普通 AUTO、Vision、Chrome / Edge 扩展 DOM 和固定离线 Demo 无需安装 Playwright Chromium。受管理的本地 DOM Demo 需要 Chromium。

## 源码安装（PowerShell 详细步骤）

### 1. 下载并解压源码

在 [GitHub 仓库](https://github.com/billstar0128-jpg/AutoQuestion) 点绿色 **Code** 按钮，再点 **Download ZIP**。下载后右键 ZIP，选择 **全部解压**，进入解压后的 AutoQuestion 文件夹。例如，若 `D:\Projects\AutoQuestion\main.py` 存在，项目根目录就是 `D:\Projects\AutoQuestion`。该目录还应有 `requirements.txt`、`README.md`、`src` 和 `tests`。

### 2. 在源码文件夹打开 PowerShell

保持资源管理器停在能直接看到 `main.py` 的这一层。点顶部地址栏，输入 `powershell` 后按 Enter。如果提示符停在上一层，例如 `PS D:\Projects>`，可输入 `cd AutoQuestion` 进入项目。路径含空格时，请用引号括起路径。输入 `dir` 检查当前目录，应能看到 `main.py` 和 `requirements.txt`。

### 3. 创建独立的 Python 环境

复制以下命令并按 Enter。运行结束后，源码目录会多出 `.venv-win` 文件夹。

```powershell
python -m venv .venv-win
```

若找不到 `python`，请检查 Windows 版 Python 是否已安装、安装器是否已将 Python 加到 PATH。Python Launcher 可用时，也可执行 `py -3 -m venv .venv-win`。可用 `python --version` 或 `py -3 --version` 核对版本。

### 4. 安装运行依赖

```powershell
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
```

初次安装需要网络。等 PowerShell 重新出现提示符后继续。若报错，可将最后几行脱敏后的错误提交到 [GitHub Issues](https://github.com/billstar0128-jpg/AutoQuestion/issues)，先移除用户名、本地私人路径和任何凭据。

### 5. 第一次运行

```powershell
.\.venv-win\Scripts\python.exe main.py
```

没有有效模型配置时会进入设置向导。选择服务商、填写 API Base URL 和 Model ID、确认模型的图片能力、选择输入模式并安全输入自己的 Key。一般选 AUTO。Windows Credential Manager 可保存 Key，也可选仅本次使用，下次只需重新输入 Key。键盘输入隐藏或显示为星号。模型、费用与配置步骤见 [API 配置指南](API_SETUP.md)。

AUTO 或 Vision 向导结束后询问是否打开本地 Demo。直接按 Enter 会进入 READY。把有权分析的题目窗口放在前台并按 F8。按 ESC 或 Ctrl+C 可停止接收任务，已有同步请求会等完成或超时再清理。固定离线 Demo 无需 Key。

若希望使用桌面窗口，可双击 `AutoQuestion.pyw`，或将上面的 `main.py` 命令加上 `--ui`。首次双击入口会询问是否准备虚拟环境和安装依赖。桌面窗口与配置见 [Windows 使用指南](WEB_UI.md)。

## 演示和诊断

- 不调用模型的固定 Demo 只回答内置示例题。终端选择 **Offline Demo**，进入 READY 后直接按 F8。固定答案中的置信度是预置值。
- 受管理的本地 DOM Demo 先安装 Chromium，再运行 `main.py --open-demo`。配合 Fake 配置可离线验证内置 DOM 样例，包括“同屏两道题”示例。Fake 不处理 Canvas 或窗口图片。真实模型配置可能产生服务商费用。普通 Chrome / Edge 使用 [可选扩展](BROWSER_DOM_SETUP.md)。
- 六道客观题可核对单选、多选和判断。[页面源码](../examples/browser_dom/mixed_questions.html) · [在线练习](https://billstar0128-jpg.github.io/AutoQuestion/try-questions.html)
- 主客观混合题可核对双空填空、简答和解方程，包括逐空复制和保留答案换行。[页面源码](../examples/browser_dom/mixed_subjective.html) · [在线练习](https://billstar0128-jpg.github.io/AutoQuestion/try-subjective.html)

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
.\.venv-win\Scripts\python.exe -m playwright install chromium
.\.venv-win\Scripts\python.exe main.py --open-demo
```

其他管理命令可在同一个 PowerShell 中运行。

```powershell
.\.venv-win\Scripts\python.exe main.py --setup
.\.venv-win\Scripts\python.exe main.py --show-config
.\.venv-win\Scripts\python.exe main.py --doctor
.\.venv-win\Scripts\python.exe main.py --version
.\.venv-win\Scripts\python.exe main.py --reset-config
```

`--reset-config` 先确认清除普通配置，再单独确认是否删除本应用保存的凭据。Doctor 仅检查本机环境、依赖和凭据元数据，Chromium 检查使用独立的无界面探针。Doctor 不发模型请求、不读真实 Key 值、不注册热键或截取屏幕。分享输出前请检查解释器路径。配置优先级及退出码见 [高级配置](CONFIGURATION.md)。

## 已有自动检查

本机请顺序运行，避免热键、浏览器桥接端口和前台焦点互相干扰。开始前关闭 AutoQuestion，确保 F8、ESC 和 37841 端口空闲。开发依赖和 Chromium 初次安装需要网络，项目已有测试使用合成数据、Fake 或 Mock 接口。

```powershell
python -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
$env:PLAYWRIGHT_BROWSERS_PATH = '0'
.\.venv-win\Scripts\python.exe -m playwright install chromium
.\.venv-win\Scripts\python.exe -m pytest -q
.\.venv-win\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-win\Scripts\python.exe -m compileall -q main.py src tests tools
.\.venv-win\Scripts\python.exe -m pip check
.\.venv-win\Scripts\python.exe tools/release_audit.py
.\.venv-win\Scripts\python.exe main.py --doctor
.\.venv-win\Scripts\python.exe main.py --version
```

Windows CI 使用临时 AppData、只读权限和 Python 版本矩阵。`AUTOQUESTION_CI=1` 仅跳过需要交互 Windows 桌面的用例，其余测试仍运行，包括通过真实 headless Chromium 验证扩展协议及模拟站点授权。在本机运行完整套件时应清除该变量。真实浏览器安装权限弹窗、物理 F8、可见窗口捕获和真实 Provider 效果需要各自的人工验证。[Windows CI](https://github.com/billstar0128-jpg/AutoQuestion/actions/workflows/ci.yml)

包含真实可见桌面窗口的检查需在交互终端单独运行。第一项使用自建窗口、合成像素和 Mock Provider。第二项使用独立临时配置、合成凭据、Fake 答案和本应用的 WM_HOTKEY，检查重复启动和关闭窗口的退出行为。窗口无法取得前台时检查会停止。冻结 EXE 也支持 `--desktop-self-test`。

```powershell
.\.venv-win\Scripts\python.exe -X utf8 tests/smoke_browser_window.py -v
.\.venv-win\Scripts\python.exe tools/desktop_entry.py --desktop-self-test logs/native-check.json
```

`.\.venv-win\Scripts\python.exe tools/clean_room.py` 会审查并复制候选源码到项目外的临时目录，准备新的虚拟环境、Chromium 和隔离的 AppData，然后执行安装、Doctor、离线 Setup 与测试。它不会复制现有配置、浏览器状态或 Key，验证目录会保留供人工检查。如果要验证公开 Git 分发，请另外从实际 Git 地址克隆。

## 构建与版本来源

- Windows 运行版本由 CLI 和 `pyproject.toml` 共同读取。`pip install --no-deps -e .` 可独立查看包元数据。Demo、Doctor 仍依赖完整源码布局。[Windows 版本定义](../src/autoquestion/__init__.py)
- GitHub Pages 静态下载页导出到 `dist/site/`。Android 具有独立的版本名和 `versionCode`。[网站导出](../tools/build_web_preview.py) · [Android 版本定义](../android/app/build.gradle)
- `requirements.txt` 提供运行依赖，`requirements-dev.txt` 增加 pytest。Pydantic 用于结构化校验，OpenAI SDK 用于兼容接口，MSS 与 Pillow 用于窗口图像，Playwright 用于受管理 DOM，websockets 用于本机桥接，pywebview 用于 Windows 工作台。
- 发布与许可核对见 [发布检查表](RELEASE_CHECKLIST.md)。模块职责和答案数据结构见 [架构](ARCHITECTURE.md)及[协议说明](TECHNICAL_NOTES.md)。

### 构建 Windows 便携程序

在 Windows x64 使用全新的构建虚拟环境。该环境保留运行依赖和 PyInstaller，避免带入开发环境的浏览器缓存及其他本地数据。

```powershell
python -m venv .venv-build-win
.\.venv-build-win\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
.\.venv-build-win\Scripts\python.exe tools/build_windows_app.py
```

打包脚本先审查源码，构建时获取 Tcl 和 WebView2 SDK 的许可文本。完成后可从 `dist/windows/AutoQuestion/` 运行 EXE，发布打包时应保留完整目录以及包内的许可证声明。[Windows 打包脚本](../tools/build_windows_app.py)。
