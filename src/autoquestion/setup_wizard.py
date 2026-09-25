"""Offline, data-driven setup; persistence happens only after confirmation."""
from dataclasses import dataclass, field
import sys

from pydantic import SecretStr, ValidationError
from .config import ConfigError, APISettingsError, load_llm_config, validate_base_url, validate_model_id
from .credentials import CredentialError, new_identifier
from .provider_presets import PRESETS, PROTOCOLS, get_preset
from .secret_input import read_secret
from .user_config import UserConfig, UserConfigError


class SetupCancelled(Exception):
    pass


class Console:
    def __init__(self, input_fn=None, output=None, secret_fn=None, interactive=None):
        self.input_fn = input if input_fn is None else input_fn
        self.output = print if output is None else output
        self.secret_fn = read_secret if secret_fn is None else secret_fn
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

    def require_interactive(self):
        if not self.interactive:
            raise ConfigError('需要交互式设置；请在 Windows Terminal 运行 main.py --setup，或提供完整环境变量配置。')

    def ask(self, prompt, default='', *, strip_value=True):
        self.require_interactive()
        value = self.input_fn(f'{prompt}' + (f' [{default}]' if default else '') + ': ')
        if strip_value:
            value = value.strip()
        if value.strip().lower() in {'cancel', 'q', 'quit'}:
            raise SetupCancelled()
        return value or default

    def validated(self, prompt, validator, default=''):
        while True:
            value = self.ask(prompt, default, strip_value=False)
            try:
                return validator(value)
            except APISettingsError as exc:
                self.output(str(exc))

    def choose(self, prompt, choices, default='1'):
        while True:
            self.output(prompt)
            for index, label in enumerate(choices, 1):
                self.output(f'{index}. {label}')
            answer = self.ask('Selection (cancel to exit)', default)
            if answer.isascii() and answer.isdigit() and 1 <= int(answer) <= len(choices):
                return int(answer)
            self.output('请选择列表中的编号。')

    def yes(self, prompt, default=False):
        while True:
            value = self.ask(prompt + (' [Y/n]' if default else ' [y/N]'), 'y' if default else 'n').lower()
            if value in {'y', 'yes'}:
                return True
            if value in {'n', 'no'}:
                return False
            self.output('请输入 Y 或 N。')

    def secret(self):
        self.require_interactive()
        while True:
            try:
                value = self.secret_fn()
                if not isinstance(value, SecretStr):
                    raise ConfigError('Secret input helper 返回类型无效。')
                raw = value.get_secret_value().strip()
                if not raw or any(ord(c) < 32 or ord(c) == 127 for c in raw) or len(raw.encode('utf-8')) > 2560:
                    self.output('Key 不能为空、含控制字符或超过 2560 UTF-8 字节；请重新输入。')
                    continue
                return SecretStr(raw)
            except UnicodeError:
                self.output('Key 编码无效，请重新粘贴。')


@dataclass(frozen=True)
class SetupResult:
    config: UserConfig
    session_secret: SecretStr | None = field(default=None, repr=False)


def updated(config, **changes):
    return UserConfig.model_validate(config.model_dump() | changes)


def summary(config, output, credential_status):
    preset = get_preset(config.provider_profile)
    output('Configuration Summary')
    output(f'Provider: {config.display_name or preset.display_name}')
    output(f'Protocol: {PROTOCOLS[config.protocol_provider]}')
    if config.protocol_provider != 'fake':
        output(f'Base URL: {config.base_url}')
        output(f'Model: {config.model}')
    output(f'Vision: {"Enabled" if config.supports_vision else "Disabled"}')
    output(f'Input mode: {config.input_mode.upper()}')
    output(f'API Key: {credential_status}')


def save_configuration(store, backend, config, secret=None):
    """Copy-on-write credential: existing IDs are never overwritten/deleted.

    A newly allocated credential is rolled back if config persistence fails.
    An already committed config remains paired with its credential on interrupt.
    """
    created = None
    if secret is not None and config.credential_mode == 'stored':
        created = new_identifier(config.provider_profile)
        config = updated(config, credential_id=created)
    try:
        if created:
            backend.put(created, secret)
        store.save(config)
    except BaseException:
        if created:
            try:
                try:
                    committed = store.load()
                except UserConfigError:
                    committed = None  # Recovering an already damaged old config.
                if committed is None or committed.credential_id != created:
                    backend.delete(created)
            except Exception:
                raise UserConfigError('保存未完成，旧配置/凭据未被替换；新凭据清理未确认，请用 --reset-config 检查。') from None
        raise
    saved = store.load()  # Same formal loader as subsequent normal starts.
    if saved is None:
        raise UserConfigError('保存后无法重新加载配置。')
    return SetupResult(saved, secret if config.credential_mode == 'session' else None)


def persist_with_choices(store, backend, config, secret, console):
    while True:
        try:
            return save_configuration(store, backend, config, secret)
        except CredentialError:
            console.output('Secure credential storage is unavailable. 不会把 Key 写入 JSON。')
            choice = console.choose('Choose:', ('Session-only mode', 'Retry', 'Cancel'))
            if choice == 1:
                config = updated(config, credential_mode='session', credential_id='')
            elif choice == 3:
                raise SetupCancelled()


def run_setup(store, backend, console, existing=None):
    console.require_interactive()
    console.output('AutoQuestion First-time Setup / Setup')
    if existing is None:
        console.output('No valid saved configuration was found.')
    console.output('只做本地结构验证，不验证 Key 真伪、不联网拉模型。输入 cancel 或 Ctrl+C 取消。')
    presets = tuple(PRESETS.values())
    default = str(next((i for i, p in enumerate(presets, 1) if existing and p.id == existing.provider_profile), 1))
    preset = presets[console.choose('Choose your AI provider:', tuple(p.display_name for p in presets), default)-1]
    console.output(preset.notes)
    if preset.protocol_provider == 'fake':
        config = UserConfig(provider_profile=preset.id, protocol_provider='fake', input_mode='demo', credential_mode='none')
        secret = None
    else:
        previous = existing if existing and existing.provider_profile == preset.id else None
        display = ''
        if preset.id == 'custom_openai_compatible':
            default_name = previous.display_name if previous else ''
            while True:
                display = console.ask('Optional display name', default_name)
                if len(display) <= 80 and not any(ord(c) < 32 or ord(c) == 127 for c in display):
                    break
                console.output('显示名最多 80 个字符，不能包含控制字符；请重新输入。')
                default_name = ''
        base_url = previous.base_url if previous else preset.default_base_url
        model = previous.model if previous else preset.suggested_model
        vision = previous.supports_vision if previous else preset.default_supports_vision
        mode = previous.input_mode if previous else 'auto'
        while True:
            if preset.allow_custom_base_url:
                base_url = console.validated('API Base URL (Enter keeps suggested value)', validate_base_url, base_url)
            if preset.allow_custom_model:
                model = console.validated('Model ID (enter an available model ID)', validate_model_id, model)
            vision = console.yes('Supports image input for THIS model?', vision)
            modes = ('auto', 'vision', 'dom', 'demo')
            mode = modes[console.choose('Input mode:', ('AUTO (recommended)', 'Vision', 'DOM', 'Demo'), str(modes.index(mode)+1))-1]
            try:
                config = UserConfig(provider_profile=preset.id, protocol_provider=preset.protocol_provider,
                                    display_name=display, base_url=base_url, model=model,
                                    supports_vision=vision, input_mode=mode,
                                    timeout_seconds=previous.timeout_seconds if previous else 30.0,
                                    image_max_edge=previous.image_max_edge if previous else 2048)
            except (ValidationError, ConfigError):
                console.output('配置无效：URL 必须是不含凭据/查询参数的 HTTP(S) API root；Model 必填；文本不能含控制字符。请重新输入。')
                continue
            if vision or mode not in {'auto', 'vision'}:
                break
            console.output('Warning: 当前模型未启用图片输入。AUTO fallback 可能失败；VISION 需要图片能力。')
            choice = console.choose('Choose:', ('Change Vision support', 'Change model', 'Change input mode', 'Continue anyway'))
            if choice == 4:
                break
            # Repeat editable fields, preserving current suggestions; never force vision on.
        secret = None
        stored_id = ''
        try:
            if previous and previous.credential_mode == 'stored' and backend.exists(previous.credential_id):
                stored_id = previous.credential_id
            else:
                candidates = tuple(name for name in backend.list_ids() if name.startswith(f'AutoQuestion/{preset.id}/'))
                if len(candidates) == 1:
                    stored_id = candidates[0]
                elif candidates:
                    console.output('该 Provider 有多个旧凭据，无法确定当前账户；请重新输入 Key。旧凭据仍保留。')
        except CredentialError:
            console.output('Secure credential storage is unavailable; session-only 仍可使用。')
        if stored_id:
            console.output('API Key: Already configured (value not displayed).')
            action = console.choose('API Key:', ('Keep existing', 'Replace', 'Use session-only key', 'Remove / switch offline'))
            if action == 1:
                if previous and previous.base_url != config.base_url:
                    if not console.yes('API 地址已变化，仍将现有 Key 用于此地址？', False):
                        raise SetupCancelled()
                config = updated(config, credential_mode='stored', credential_id=stored_id)
            elif action == 4:
                # Switching offline does not silently delete any existing credential.
                console.output('将切换 Offline Demo；旧凭据保留。需要删除时运行 --reset-config 并明确确认。')
                config = UserConfig(provider_profile='offline_demo', protocol_provider='fake', input_mode='demo', credential_mode='none')
            else:
                secret = console.secret()
                config = updated(config, credential_mode='stored' if action == 2 else 'session',
                                 credential_id=new_identifier(preset.id) if action == 2 else '')
        else:
            secret = console.secret()
            action = console.choose('API Key storage:', ('Windows Credential Manager (recommended)', 'Session-only', 'Cancel'))
            if action == 3:
                raise SetupCancelled()
            config = updated(config, credential_mode='stored' if action == 1 else 'session',
                             credential_id=new_identifier(preset.id) if action == 1 else '')
        if secret is not None:
            # Reject accidentally pasting the same secret into public fields.
            if secret.get_secret_value() in config.model_dump_json():
                raise ConfigError('Key 不能出现在普通配置字段中；设置未保存。')
            load_llm_config(config.to_env() | {'LLM_API_KEY': secret.get_secret_value()})
    status = {'stored': 'configured securely (save pending)', 'session': 'session-only', 'none': 'not required'}[config.credential_mode]
    summary(config, console.output, status)
    if not console.yes('Save configuration?', True):
        raise SetupCancelled()
    result = persist_with_choices(store, backend, config, secret, console)
    console.output('Configuration saved securely.' if result.config.credential_mode == 'stored'
                   else 'Configuration saved. API Key is session-only.' if result.config.credential_mode == 'session'
                   else 'Offline configuration saved.')
    return result
