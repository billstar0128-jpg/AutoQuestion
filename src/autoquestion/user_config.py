"""Versioned non-secret user settings and atomic persistence."""
import json
import os
from pathlib import Path
import tempfile

from pydantic import BaseModel, ConfigDict, Field, model_validator
from .config import ConfigError, APISettingsError, load_config, load_llm_config, validate_api_settings
from .credentials import valid_identifier
from .provider_presets import PROTOCOLS, get_preset


class UserConfigError(ConfigError):
    pass


class UserConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, hide_input_in_errors=True)
    config_version: int = 1
    provider_profile: str
    protocol_provider: str
    display_name: str = Field(default='', repr=False, max_length=80)
    base_url: str = Field(default='', repr=False, max_length=2048)
    model: str = Field(default='', repr=False, max_length=256)
    supports_vision: bool = False
    input_mode: str = 'auto'
    timeout_seconds: float = 30.0
    image_max_edge: int = 2048
    credential_mode: str = 'session'
    credential_id: str = Field(default='', repr=False)

    @model_validator(mode='before')
    @classmethod
    def normalize_api_settings(cls, data):
        if isinstance(data, dict) and data.get('protocol_provider') == 'openai':
            base_url, model = validate_api_settings(data.get('base_url', ''), data.get('model', ''))
            return data | {'base_url': base_url, 'model': model}
        return data

    @model_validator(mode='after')
    def validate_settings(self):
        if self.config_version != 1:
            raise ValueError('未知 config_version；请升级程序或运行 --setup。')
        if self.protocol_provider not in PROTOCOLS:
            raise ValueError('当前版本未实现该 protocol_provider。')
        preset = get_preset(self.provider_profile)
        if preset.protocol_provider != self.protocol_provider:
            raise ValueError('Provider profile 与 protocol 不一致。')
        if any(any(ord(c) < 32 or ord(c) == 127 for c in text) for text in (self.display_name, self.model, self.base_url)):
            raise ValueError('配置文本不能包含控制字符。')
        if self.credential_mode not in {'stored', 'session', 'none'}:
            raise ValueError('Credential mode 无效。')
        if self.credential_mode == 'stored':
            if not valid_identifier(self.credential_id) or not self.credential_id.startswith(f'AutoQuestion/{self.provider_profile}/'):
                raise ValueError('Credential reference 无效。')
        elif self.credential_id:
            raise ValueError('非持久凭据不能包含 credential reference。')
        values = self.to_env()
        load_config(values)
        if self.protocol_provider == 'openai':
            if self.credential_mode == 'none':
                raise ValueError('API profile 需要 stored 或 session 凭据模式。')
            load_llm_config(values | {'LLM_API_KEY': 'test-api-key'})
        elif (self.base_url or self.model or self.supports_vision or self.credential_mode != 'none'
              or self.input_mode != 'demo'):
            raise ValueError('Offline Demo 仅使用 fake/demo，不需要 API 配置。')
        return self

    @property
    def capabilities(self):
        return frozenset({'text', 'vision'} if self.supports_vision else {'text'})

    def to_env(self):
        return {'LLM_PROVIDER': self.protocol_provider, 'LLM_BASE_URL': self.base_url,
                'LLM_MODEL': self.model, 'LLM_SUPPORTS_VISION': str(self.supports_vision).lower(),
                'INPUT_MODE': self.input_mode, 'LLM_TIMEOUT_SECONDS': str(self.timeout_seconds),
                'IMAGE_MAX_EDGE': str(self.image_max_edge)}


def config_path(environ=None):
    values = os.environ if environ is None else environ
    location = values.get('APPDATA')
    if not location or not Path(location).is_absolute():
        raise UserConfigError('无法定位用户 AppData；可使用有效环境变量配置运行。')
    return Path(location) / 'AutoQuestion' / 'config.json'


class UserConfigStore:
    def __init__(self, path=None):
        self.path = config_path() if path is None else Path(path)

    def load(self):
        try:
            if not self.path.exists():
                return None
            if self.path.stat().st_size > 65536:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.get('config_version') != 1:
                raise UserConfigError('Saved configuration config_version 无效或尚未支持；请运行 --setup。')
            if data.get('protocol_provider') == 'openai':
                validate_api_settings(data.get('base_url', ''), data.get('model', ''))
            return UserConfig.model_validate(data)
        except UserConfigError:
            raise
        except APISettingsError as exc:
            raise UserConfigError(f'Saved AutoQuestion configuration is invalid. {exc} 请运行 --setup。') from None
        except (OSError, UnicodeError, ValueError, ConfigError):
            raise UserConfigError('Saved AutoQuestion configuration is invalid；请运行 --setup 或 --reset-config。') from None

    def save(self, config):
        temporary = None
        try:
            validated = UserConfig.model_validate(config.model_dump())
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent,
                                             prefix='.config-', suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(validated.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except (OSError, ValueError, ConfigError):
            raise UserConfigError('无法保存用户配置；原文件保持不变，请检查目录权限。') from None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def reset(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise UserConfigError('无法删除用户配置，请检查目录权限。') from None
