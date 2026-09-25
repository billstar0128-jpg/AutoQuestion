"""User-facing presets, distinct from implemented wire protocols.

API roots checked against vendor quickstarts; model IDs deliberately require
user input until verified with this application's request/answer contract.
"""
from dataclasses import dataclass
import re
from types import MappingProxyType

from pydantic import SecretStr
from .config import ConfigError, LLMConfig

PROTOCOLS = MappingProxyType({'openai': 'OpenAI-compatible', 'fake': 'Offline Fake'})


@dataclass(frozen=True)
class ProviderPreset:
    id: str
    display_name: str
    protocol_provider: str
    default_base_url: str = ''
    suggested_model: str = ''
    default_supports_vision: bool = False
    allow_custom_base_url: bool = True
    allow_custom_model: bool = True
    notes: str = '请填写账户可用的 Model ID，并确认该模型是否支持图片；本项目未验证所有模型。'

    def __post_init__(self):
        if (not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', self.id)
                or not self.display_name.strip() or self.protocol_provider not in PROTOCOLS
                or any(type(value) is not bool for value in (self.default_supports_vision,
                           self.allow_custom_base_url, self.allow_custom_model))):
            raise ConfigError('Provider preset 定义无效。')
        if self.default_base_url:
            LLMConfig(SecretStr('test-api-key'), self.default_base_url, self.suggested_model or 'test-model')
        if self.protocol_provider != 'fake' and ((not self.allow_custom_base_url and not self.default_base_url)
                or (not self.allow_custom_model and not self.suggested_model)):
            raise ConfigError('不可编辑的 API preset 字段必须提供有效默认值。')
        if self.protocol_provider == 'fake' and (self.default_base_url or self.suggested_model or self.default_supports_vision):
            raise ConfigError('Offline preset 不能配置真实 API。')


def build_registry(presets):
    result = {}
    for preset in presets:
        if not isinstance(preset, ProviderPreset) or preset.id in result:
            raise ConfigError('Provider preset 类型无效或 ID 重复。')
        result[preset.id] = preset
    return MappingProxyType(result)


PRESETS = build_registry((
    ProviderPreset('deepseek', 'DeepSeek', 'openai', 'https://api.deepseek.com'),
    ProviderPreset('kimi', 'Kimi / Moonshot', 'openai', 'https://api.moonshot.cn/v1'),
    ProviderPreset('zhipu', 'Zhipu / GLM', 'openai', 'https://open.bigmodel.cn/api/paas/v4/'),
    ProviderPreset('openai', 'OpenAI / GPT', 'openai', 'https://api.openai.com/v1'),
    ProviderPreset('custom_openai_compatible', 'Custom OpenAI-compatible API', 'openai'),
    ProviderPreset('offline_demo', 'Offline Demo', 'fake', allow_custom_base_url=False,
                   allow_custom_model=False, notes='无需 API Key、网络请求或 Chromium runtime。'),
))


def get_preset(identifier):
    try:
        return PRESETS[identifier]
    except (KeyError, TypeError):
        raise ConfigError('未知 Provider profile；请运行 --setup。') from None
