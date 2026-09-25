"""只读本地诊断；不导入 app、热键、截图或 Provider，不读取 .env/Key 值。"""
from contextlib import redirect_stderr, redirect_stdout
from collections import ChainMap
from dataclasses import dataclass
import importlib
import importlib.metadata
from io import StringIO
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import warnings

from .secret_safety import scan_project

ROOT = Path(__file__).resolve().parents[2]
PACKAGES = (('pydantic', 'pydantic'), ('openai', 'openai'), ('mss', 'mss'),
            ('Pillow', 'PIL.Image'), ('python-dotenv', 'dotenv'), ('playwright', 'playwright.sync_api'))
PUBLIC_CONFIG = ('HOTKEY', 'EXIT_KEY', 'DEBOUNCE_MS', 'INPUT_MODE', 'IMAGE_MAX_EDGE',
                 'LLM_PROVIDER', 'LLM_BASE_URL', 'LLM_MODEL', 'LLM_SUPPORTS_VISION', 'LLM_TIMEOUT_SECONDS')


@dataclass(frozen=True)
class Check:
    level: str
    message: str


def dependency_check(distribution, module):
    try:
        # 导入失败只报告固定错误，第三方 import 的输出/警告不透传。
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            importlib.import_module(module)
        version = importlib.metadata.version(distribution)
        return Check('OK', f'{distribution} {version}')
    except Exception:
        return Check('FAIL', f'{distribution} unavailable; install requirements.txt with .venv-win')


def chromium_check(environ):
    if sys.platform != 'win32':
        return Check('WARN', 'Chromium launch probe requires Windows; skipped')
    # 只传启动必需的非凭据变量，绝不复制整个 os.environ 或读取 Key。
    names = ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA')
    present = {name.upper(): name for name in environ}
    child_env = {name: environ[present[name]] for name in names if name in present}
    child_env.update(PYTHONPATH=str(ROOT / 'src'), PYTHONIOENCODING='utf-8',
                     PYTHONDONTWRITEBYTECODE='1', PLAYWRIGHT_BROWSERS_PATH=environ.get('PLAYWRIGHT_BROWSERS_PATH', '0'))
    try:
        result = subprocess.run([sys.executable, '-m', 'autoquestion.doctor_browser'],
            env=child_env, cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
            timeout=25, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode == 0 and json.loads(result.stdout) == {'ok': True}:
            return Check('OK', 'Chromium runtime: isolated headless launch / close passed')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return Check('FAIL', 'Chromium runtime check failed; set PLAYWRIGHT_BROWSERS_PATH=0 and run .venv-win Python -m playwright install chromium')


def configuration_checks(environ, *, stored_credential_available=False):
    checks = []
    # Mapping 的 __contains__ 可能调用 __getitem__；显式只遍历变量名。
    present = set(iter(environ))
    key_present = 'LLM_API_KEY' in present
    checks.append(Check('OK' if key_present or stored_credential_available else 'WARN',
        'LLM_API_KEY variable is present (value not inspected)' if key_present else
        'API credential available in Windows storage (value not inspected)' if stored_credential_available else
        'LLM_API_KEY not configured; offline demo/fake remains available'))
    public = {name: environ[name] for name in PUBLIC_CONFIG if name in present}
    try:
        from .config import load_config, load_llm_config, ConfigError
    except ImportError:
        return checks + [Check('FAIL', 'Configuration check needs working Pydantic')]
    try:
        config = load_config(public)
        checks.append(Check('OK', 'HOTKEY / EXIT_KEY / INPUT_MODE / LLM_PROVIDER / image limits valid'))
    except ConfigError as exc:
        checks.append(Check('FAIL', str(exc)))
        config = None
    # 用明确测试凭据替代真实 Key，复用现有非秘密字段验证，不创建 Provider。
    validation = dict(public, LLM_API_KEY='test-api-key')
    for name, fallback in (('LLM_BASE_URL', 'https://example.invalid/v1'), ('LLM_MODEL', 'test-model')):
        if not public.get(name, '').strip():
            if public.get('LLM_PROVIDER', 'fake').strip().lower() == 'openai':
                checks.append(Check('WARN', f'{name} not configured; real Provider cannot answer yet'))
            validation[name] = fallback
    try:
        llm = load_llm_config(validation)
        checks.append(Check('OK', 'Provider non-secret fields / timeout / supports_vision syntax valid'))
        if config and config.input_mode in {'vision', 'auto'}:
            if config.llm_provider != 'openai':
                checks.append(Check('WARN', 'Fake has no Vision; use demo/dom for offline answers, or configure OpenAI Vision'))
            elif not llm.supports_vision:
                checks.append(Check('WARN', 'Vision disabled: capture and image requests will be refused before execution'))
            else:
                checks.append(Check('OK', 'Vision configured; actual model capability not tested'))
    except ConfigError as exc:
        checks.append(Check('FAIL', str(exc)))
    return checks


def project_checks(root, cwd):
    checks = []
    required = ('main.py', 'src/autoquestion', 'requirements.txt', 'requirements-dev.txt',
                'examples/demo_quiz.html', 'examples/demo_canvas_quiz.html')
    checks.append(Check('OK' if all((root / name).exists() for name in required) else 'FAIL',
                        'Project layout complete' if all((root / name).exists() for name in required) else 'Project files missing'))
    checks.append(Check('OK' if all((cwd / name).exists() for name in required) else 'WARN',
                        'Working directory is project root' if all((cwd / name).exists() for name in required)
                        else 'Working directory is not a complete project; run from AutoQuestion root'))
    try:
        ignored = set((root / '.gitignore').read_text(encoding='utf-8-sig').splitlines())
        needed = {'.env', '.env.*', '!.env.example', '.venv-*/', 'screenshots/', 'logs/', 'legacy_main.py'}
        checks.append(Check('OK' if needed <= ignored else 'WARN', '.gitignore basic sensitive exclusions present'
                            if needed <= ignored else '.gitignore is missing recommended exclusions'))
    except (OSError, UnicodeError):
        checks.append(Check('WARN', '.gitignore missing or unreadable'))
    if not (root / '.env.example').is_file():
        checks.append(Check('WARN', '.env.example missing'))
    findings = scan_project(root)
    if findings:
        checks.extend(Check('FAIL', f'Secret safety: {item.path}:{item.line} ({item.kind}); content redacted') for item in findings)
    else:
        checks.append(Check('OK', 'Source / .env.example: no obvious credential literals (limited check)'))
    # 只检查实现，不初始化 mss 或读取屏幕；遇到实现变化需重新审查。
    try:
        source = (root / 'src/autoquestion/capture/screen.py').read_text(encoding='utf-8')
        in_memory = ('with BytesIO() as buffer:' in source and 'image.save(buffer, format="PNG")' in source
                     and all(marker not in source for marker in ('.write_bytes(', '.write_text(', 'open(', 'tempfile')))
        checks.append(Check('OK' if in_memory else 'WARN', 'Screenshot persistence disabled (in-memory capture implementation)'
                            if in_memory else 'Screenshot persistence implementation needs manual review'))
    except (OSError, UnicodeError):
        checks.append(Check('FAIL', 'Screen capture implementation missing or unreadable'))
    return checks


def user_configuration_checks(environ, *, store=None, backend=None):
    """Only validated public settings and credential metadata; no get()."""
    try:
        from .credentials import WindowsCredentials, CredentialError
        from .user_config import UserConfigStore, UserConfigError, config_path
    except ImportError:
        return [Check('FAIL', 'User configuration check needs working runtime dependencies')], {}, False
    try:
        store = UserConfigStore(config_path(environ)) if store is None else store
        saved = store.load()
    except UserConfigError as exc:
        return [Check('FAIL', str(exc))], {}, False
    if saved is None:
        return [Check('OK', 'No saved user config; normal first run offers Setup (Doctor never starts it)')], {}, False
    checks = [Check('OK', 'User config found; config_version / provider_profile / protocol_provider valid')]
    present = False
    if saved.credential_mode == 'stored':
        try:
            backend = WindowsCredentials() if backend is None else backend
            present = backend.exists(saved.credential_id)
            checks.append(Check('OK' if present else 'WARN', 'Credential available (metadata only)' if present else 'Credential missing'))
        except CredentialError:
            checks.append(Check('WARN', 'Secure credential storage unavailable; session-only is possible'))
    elif saved.credential_mode == 'session':
        checks.append(Check('WARN', 'No persistent API credential found (session-only)'))
    else:
        checks.append(Check('OK', 'Offline Demo requires no API credential'))
    return checks, saved.to_env(), present


def run_doctor(*, environ=None, root=None, cwd=None, env_file_requested=False):
    values = os.environ if environ is None else environ
    project = ROOT if root is None else Path(root)
    checks = [Check('OK' if sys.platform == 'win32' else 'FAIL', f'Operating system: {platform.system()} (Windows required)'),
              Check('OK' if sys.version_info >= (3, 10) else 'FAIL', f'Python {platform.python_version()} (3.10+ required)'),
              Check('OK', f'Python executable: {sys.executable}')]
    prefix = Path(sys.prefix).name.lower()
    checks.append(Check('OK' if prefix == '.venv-win' else 'WARN', 'Recommended .venv-win active' if prefix == '.venv-win'
                        else 'Interpreter is not recommended .venv-win; old .venv / system Python may be incompatible'))
    if env_file_requested:
        checks.append(Check('WARN', 'Doctor does not read --env-file; checking process environment only'))
    checks.extend(dependency_check(distribution, module) for distribution, module in PACKAGES)
    user_checks, saved_values, credential_available = user_configuration_checks(values)
    checks.extend(user_checks)
    checks.extend(configuration_checks(ChainMap(values, saved_values), stored_credential_available=credential_available))
    checks.extend(project_checks(project, Path.cwd() if cwd is None else Path(cwd)))
    checks.append(chromium_check(values))
    for check in checks:
        print(f'[{check.level}] {check.message}')
    result = 'FAIL' if any(c.level == 'FAIL' for c in checks) else 'WARNINGS' if any(c.level == 'WARN' for c in checks) else 'PASS'
    print(f'\nDoctor result:\n{result}')
    return 1 if result == 'FAIL' else 0
