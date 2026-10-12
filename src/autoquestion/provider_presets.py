"""User-facing presets, distinct from implemented wire protocols.

API roots and illustrative model IDs checked against vendor docs (2026-10-13).
Examples do not select a model or certify real-provider compatibility.
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
    example_models: tuple[str, ...] = ()
    vision_notes: str = '图片能力取决于具体模型；以服务商文档和账户权限为准。'
    docs_url: str = ''

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
    ProviderPreset('deepseek', 'DeepSeek', 'openai', 'https://api.deepseek.com',
                   example_models=('deepseek-flash', 'deepseek-v4-pro'),
                   vision_notes='官方文档说明 deepseek-flash 支持图片输入；其他模型请单独确认。',
                   docs_url='https://api-docs.deepseek.com/'),
    ProviderPreset('kimi', 'Kimi / Moonshot', 'openai', 'https://api.moonshot.cn/v1',
                   example_models=('kimi-k3', 'kimi-k2.6'),
                   vision_notes='官方文档说明 kimi-k3 / kimi-k2.6 支持图片输入；账户可用性需单独确认。',
                   docs_url='https://platform.kimi.com/docs/get-api-key'),
    ProviderPreset('zhipu', 'Zhipu / GLM', 'openai', 'https://open.bigmodel.cn/api/paas/v4/',
                   example_models=('glm-4.6v', 'glm-4.6v-flash'),
                   vision_notes='GLM 的文本模型与视觉模型不同；示例为视觉系列，勿凭名称给其他模型开启图片能力。',
                   docs_url='https://docs.bigmodel.cn/api-reference/模型-api/对话补全'),
    ProviderPreset('openai', 'OpenAI / GPT', 'openai', 'https://api.openai.com/v1',
                   example_models=('gpt-4.1-mini', 'gpt-4.1-mini-2025-04-14'),
                   vision_notes='官方文档说明 gpt-4.1-mini 支持图片输入；ChatGPT 订阅与 API 额度分开。',
                   docs_url='https://developers.openai.com/api/docs/models/gpt-4.1-mini'),
    ProviderPreset('custom_openai_compatible', 'Custom OpenAI-compatible API', 'openai'),
    ProviderPreset('offline_demo', 'Offline Demo', 'fake', allow_custom_base_url=False,
                   allow_custom_model=False, notes='无需 API Key、网络请求或 Chromium runtime。'),
))


def public_presets():
    """Non-secret examples shared by console setup, local UI and online preview."""
    return [dict(id=p.id, name=p.display_name, base_url=p.default_base_url,
                 models=list(p.example_models), vision_notes=p.vision_notes,
                 docs_url=p.docs_url, notes=p.notes) for p in PRESETS.values()]


def get_preset(identifier):
    try:
        return PRESETS[identifier]
    except (KeyError, TypeError):
        raise ConfigError('未知 Provider profile；请运行 --setup。') from None
