"""Startup boundary: merge settings without putting secrets in os.environ."""
from contextlib import redirect_stderr
from dataclasses import dataclass, field, replace
from io import StringIO
import os

from .config import Config, ConfigError, load_config, load_llm_config
from .credentials import CredentialError, WindowsCredentials
from .provider_presets import PROTOCOLS, get_preset
from .setup_wizard import Console, SetupCancelled, run_setup
from .user_config import UserConfigError, UserConfigStore, config_path

ENV_FIELDS = ('HOTKEY', 'EXIT_KEY', 'DEBOUNCE_MS', 'INPUT_MODE', 'IMAGE_MAX_EDGE',
              'LLM_PROVIDER', 'LLM_API_KEY', 'LLM_BASE_URL', 'LLM_MODEL',
              'LLM_SUPPORTS_VISION', 'LLM_TIMEOUT_SECONDS')


@dataclass(frozen=True)
class RuntimeSettings:
    config: Config = field(repr=False)
    display_name: str
    credential_status: str
    open_demo: bool = False


def explicit_values(environ, env_file=None, *, inspect_secret=True):
    values = {}
    if env_file is not None:
        from dotenv import dotenv_values
        try:
            if not env_file.is_file():
                raise ConfigError('指定的配置文件不存在。')
            with redirect_stderr(StringIO()):
                data = dotenv_values(env_file, interpolate=False, encoding='utf-8-sig')
            values.update((key, value) for key, value in data.items() if key in ENV_FIELDS and value is not None)
            if not inspect_secret and 'LLM_API_KEY' in values:
                values['LLM_API_KEY'] = 'test-api-key'
        except (OSError, UnicodeError):
            raise ConfigError('无法读取指定的配置文件。') from None
    present = set(iter(environ))
    values.update((key, environ[key] if inspect_secret or key != 'LLM_API_KEY' else 'test-api-key')
                  for key in ENV_FIELDS if key in present)
    return values


def runnable_explicit(values):
    config = load_config(values)
    if config.llm_provider == 'fake':
        return bool({'INPUT_MODE', 'LLM_PROVIDER'} & values.keys())
    try:
        load_llm_config(values)
        return True
    except ConfigError:
        return False


def resolve_startup(args, *, store=None, backend=None, console=None, environ=None):
    env = os.environ if environ is None else environ
    console = Console() if console is None else console
    backend = WindowsCredentials() if backend is None else backend
    explicit = explicit_values(env, args.env_file)
    # Invalid explicit modes/hotkeys are configuration errors, not wizard defaults.
    load_config(explicit)
    try:
        store = UserConfigStore(config_path(env)) if store is None else store
    except UserConfigError:
        if args.setup or not runnable_explicit(explicit):
            raise
        return build_runtime(explicit, None, None, backend, console)
    saved = None
    try:
        saved = store.load()
    except UserConfigError as exc:
        console.output(str(exc))
        console.output('不会自动覆盖文件。')
        if not args.setup and not runnable_explicit(explicit):
            choice = console.choose('Recovery:', ('Re-run Setup', 'Ignore saved config for this session (offline demo)', 'Exit'))
            if choice == 3:
                raise SetupCancelled()
            if choice == 2:
                return build_runtime({'INPUT_MODE': 'demo', 'LLM_PROVIDER': 'fake'} | explicit, None, None, backend, console)
            args.setup = True
        elif not args.setup:
            console.output('使用本次完整显式配置；损坏的保存文件保持不变。')
    session_secret = None
    configured_now = False
    if args.setup or (saved is None and not runnable_explicit(explicit)):
        if explicit:
            console.output('本次环境变量 / --env-file 将覆盖向导保存值；保存值用于以后启动。')
        result = run_setup(store, backend, console, saved)
        saved, session_secret = result.config, result.session_secret
        configured_now = True
    values = (saved.to_env() if saved else {}) | explicit
    effective = load_config(values)
    open_demo = args.open_demo
    if configured_now and effective.input_mode in {'auto', 'vision'} and not open_demo:
        open_demo = console.yes('Setup complete. Open the local demo quiz now?', False)
    elif configured_now and effective.input_mode == 'dom':
        console.output('DOM mode opens the managed local Demo automatically.')
    return replace(build_runtime(values, saved, session_secret, backend, console), open_demo=open_demo)


def build_runtime(values, saved, session_secret, backend, console):
    config = load_config(values)
    display = get_preset(saved.provider_profile).display_name if saved else PROTOCOLS[config.llm_provider]
    if saved and saved.display_name:
        display = saved.display_name
    if saved and (saved.protocol_provider != config.llm_provider or saved.base_url != values.get('LLM_BASE_URL', '')):
        display = f'{PROTOCOLS[config.llm_provider]} (explicit override)'
    status = 'not required'
    if config.llm_provider == 'openai':
        # Validate public API settings before reading a credential or prompting.
        load_llm_config(values | {'LLM_API_KEY': 'test-api-key'})
        values = dict(values)
        secret = None
        if 'LLM_API_KEY' in values:
            status = 'configured (explicit)'
        elif session_secret is not None:
            secret, status = session_secret, 'session-only'
        elif saved and saved.protocol_provider == 'openai' and saved.credential_mode == 'stored':
            try:
                secret = backend.get(saved.credential_id)
                status = 'configured securely' if secret else 'missing'
            except CredentialError:
                console.output('Secure credential storage is unavailable; 可为本次运行输入 Key。')
        if 'LLM_API_KEY' not in values:
            if secret is None:
                console.output('API Key missing / session-only: 仅询问本次 Key，不重跑完整向导。')
                secret, status = console.secret(), 'session-only'
            values['LLM_API_KEY'] = secret.get_secret_value()
        config = replace(config, llm_config=load_llm_config(values))
    console.output('Configuration loaded. Starting AutoQuestion...')
    console.output(f'Provider: {display}')
    if config.llm_config:
        console.output(f'Model: {config.llm_config.model}')
        console.output(f'Vision: {"Enabled" if config.llm_config.supports_vision else "Disabled"}')
    console.output(f'Input mode: {config.input_mode.upper()}')
    console.output(f'API Key: {status}')
    return RuntimeSettings(config, display, status)


def show_config(args, *, store=None, backend=None, console=None, environ=None):
    env = os.environ if environ is None else environ
    console = Console() if console is None else console
    backend = WindowsCredentials() if backend is None else backend
    store = UserConfigStore(config_path(env)) if store is None else store
    saved = store.load()
    explicit = explicit_values(env, args.env_file, inspect_secret=False)
    values = (saved.to_env() if saved else {}) | explicit
    config = load_config(values)
    display = (saved.display_name or get_preset(saved.provider_profile).display_name) if saved else PROTOCOLS[config.llm_provider]
    if saved and (saved.protocol_provider != config.llm_provider or saved.base_url != values.get('LLM_BASE_URL', '')):
        display = f'{PROTOCOLS[config.llm_provider]} (explicit override)'
    console.output(f'Provider: {display}')
    console.output(f'Protocol: {PROTOCOLS[config.llm_provider]}')
    console.output(f'Input mode: {config.input_mode.upper()}')
    if config.llm_provider == 'openai':
        llm = load_llm_config(values | {'LLM_API_KEY': 'test-api-key'})
        console.output(f'Base URL: {llm.base_url}')
        console.output(f'Model: {llm.model}')
        console.output(f'Vision: {"Enabled" if llm.supports_vision else "Disabled"}')
        status = 'missing'
        if 'LLM_API_KEY' in explicit:
            status = 'configured (explicit variable present; value not inspected)'
        elif saved and saved.credential_mode == 'stored':
            try:
                status = 'configured securely' if backend.exists(saved.credential_id) else 'missing'
            except CredentialError:
                status = 'storage unavailable'
        elif saved and saved.credential_mode == 'session':
            status = 'session-only; requested at startup'
        console.output(f'API Key: {status}')
    else:
        console.output('API Key: not required')
    if saved is None:
        console.output('No saved user config. --setup creates one; current display uses explicit/default settings.')
    return 0


def reset_config(*, store=None, backend=None, console=None):
    console = Console() if console is None else console
    store = UserConfigStore() if store is None else store
    backend = WindowsCredentials() if backend is None else backend
    console.require_interactive()
    if not console.yes('Reset saved AutoQuestion configuration?', False):
        raise SetupCancelled()
    remove_credentials = console.yes('Remove ALL stored AutoQuestion API credentials as well?', False)
    if remove_credentials:
        # Only the app's validated namespace, including retained old revisions.
        for identifier in backend.list_ids():
            backend.delete(identifier)
    store.reset()
    console.output('User config removed. Stored credentials removed.' if remove_credentials
                   else 'User config removed. Stored credentials retained.')
    return 0
