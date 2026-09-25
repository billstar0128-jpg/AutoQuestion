"""环境变量配置；仅显式 --env-file 时加载本地文件，不写入凭据。"""

from dataclasses import dataclass, field
import math
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from pydantic import SecretStr


class ConfigError(ValueError):
    """配置错误；错误信息不包含用户输入的原始值。"""


class APISettingsError(ConfigError):
    """Safe, field-specific structural errors shared by Setup and loaders."""


def _public_text(value: str, field_name: str, limit: int) -> str:
    if not isinstance(value, str) or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in value):
        raise APISettingsError(f'Invalid {field_name}: control characters are not allowed. Please enter it again.')
    value = value.strip()
    if not value or len(value) > limit:
        raise APISettingsError(f'Invalid {field_name}: enter a non-empty value (maximum {limit} characters).')
    return value


def validate_base_url(value: str) -> str:
    value = _public_text(value, 'API Base URL (LLM_BASE_URL)', 2048)
    try:
        url = urlsplit(value)
        valid = (url.scheme in {'http', 'https'} and url.hostname and
                 url.username is None and url.password is None and not url.query and
                 not url.fragment and not any(c.isspace() for c in value))
        _ = url.port
    except ValueError:
        valid = False
    if not valid:
        raise APISettingsError('Invalid API Base URL (LLM_BASE_URL). Use an http:// or https:// API root with a hostname, '
                               'without credentials, query or fragment. A Model ID belongs in Model ID. Please enter the Base URL again.')
    return value


def validate_model_id(value: str) -> str:
    value = _public_text(value, 'Model ID (LLM_MODEL)', 256)
    if '://' in value:
        raise APISettingsError('Invalid Model ID (LLM_MODEL). This looks like an API URL. '
                               'Please enter the model identifier provided by your AI provider.')
    return value


def validate_api_settings(base_url: str, model: str) -> tuple[str, str]:
    try:
        normalized_url = validate_base_url(base_url)
    except APISettingsError:
        try:
            validate_model_id(base_url)
            validate_base_url(model)
        except APISettingsError:
            pass
        else:
            raise APISettingsError('The API Base URL and Model ID appear to be reversed. '
                                   'Please re-enter them with --setup or correct the explicit configuration; values were not swapped.') from None
        raise
    return normalized_url, validate_model_id(model)


def virtual_key(name: str) -> int:
    """支持 ESC 和 F1～F11；F12 为 Windows 调试器保留。"""
    if name == "ESC":
        return 0x1B
    if name in {f"F{i}" for i in range(1, 12)}:
        return 0x70 + int(name[1:]) - 1
    raise ConfigError("热键只支持 ESC、F1～F11。")


@dataclass(frozen=True)
class Config:
    hotkey: str = "F8"
    exit_key: str = "ESC"
    debounce_ms: int = 400
    llm_provider: str = "fake"
    input_mode: str = "vision"
    image_max_edge: int = 2048
    llm_config: "LLMConfig | None" = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        for setting, value in (("HOTKEY", self.hotkey), ("EXIT_KEY", self.exit_key)):
            try:
                virtual_key(value)
            except ConfigError as exc:
                raise ConfigError(f"{setting}: {exc}") from None
        if self.hotkey == self.exit_key:
            raise ConfigError("HOTKEY 和 EXIT_KEY 不能相同。")
        if not 300 <= self.debounce_ms <= 500:
            raise ConfigError("DEBOUNCE_MS 必须是 300～500 的整数。")
        if self.llm_provider not in {"fake", "openai"}:
            raise ConfigError("LLM_PROVIDER 只支持 fake 或 openai。")
        if self.input_mode not in {"vision", "demo", "dom", "auto"}:
            raise ConfigError("INPUT_MODE 只支持 auto、vision、demo 或 dom。")
        if not 1024 <= self.image_max_edge <= 4096:
            raise ConfigError("IMAGE_MAX_EDGE 必须是 1024～4096 的整数。")


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """显式传入映射方便离线测试，正常启动读取 os.environ。"""
    values = os.environ if environ is None else environ
    try:
        debounce = int(values.get("DEBOUNCE_MS", "400"))
    except ValueError:
        raise ConfigError("DEBOUNCE_MS 必须是 300～500 的整数。") from None
    try:
        max_edge = int(values.get("IMAGE_MAX_EDGE", "2048"))
    except ValueError:
        raise ConfigError("IMAGE_MAX_EDGE 必须是 1024～4096 的整数。") from None
    return Config(
        hotkey=values.get("HOTKEY", "F8").strip().upper(),
        exit_key=values.get("EXIT_KEY", "ESC").strip().upper(),
        debounce_ms=debounce,
        llm_provider=values.get("LLM_PROVIDER", "fake").strip().lower(),
        input_mode=values.get("INPUT_MODE", "vision").strip().lower(),
        image_max_edge=max_edge,
    )


def load_env_file(path: Path) -> None:
    """只加载用户显式指定的文件，环境变量优先，不插值、不回显内容。"""
    from dotenv import load_dotenv

    try:
        if not path.is_file():
            raise ConfigError("指定的配置文件不存在。")
        load_dotenv(dotenv_path=path, override=False, interpolate=False, encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise ConfigError("无法读取指定的配置文件。") from None


@dataclass(frozen=True)
class LLMConfig:
    """API 配置按需加载，Fake 模式不依赖这些字段。"""

    api_key: SecretStr = field(repr=False)
    base_url: str = field(repr=False)
    model: str = field(repr=False)
    supports_vision: bool = False
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.api_key, SecretStr) or not self.api_key.get_secret_value().strip():
            raise ConfigError("LLM_API_KEY 未配置。")
        if any(char in self.api_key.get_secret_value() for char in "\r\n"):
            raise ConfigError("LLM_API_KEY 格式无效。")
        base_url, model = validate_api_settings(self.base_url, self.model)
        object.__setattr__(self, 'base_url', base_url)
        object.__setattr__(self, 'model', model)
        if not math.isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 120:
            raise ConfigError("LLM_TIMEOUT_SECONDS 必须是 1～120 的有限秒数。")


def load_llm_config(environ: Mapping[str, str] | None = None) -> LLMConfig:
    """仅在真实 Provider 被显式使用时读取；不输出配置原值。"""
    values = os.environ if environ is None else environ
    missing = [name for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL")
               if not values.get(name, "").strip()]
    if missing:
        raise ConfigError("\n".join(f"{name} 未配置。" for name in missing)
                          + "\n请在本机配置这些项目；不要将密钥发给他人。")
    vision = values.get("LLM_SUPPORTS_VISION", "false").strip().lower()
    if vision not in {"true", "false"}:
        raise ConfigError("LLM_SUPPORTS_VISION 必须为 true 或 false。")
    try:
        timeout = float(values.get("LLM_TIMEOUT_SECONDS", "30"))
    except ValueError:
        raise ConfigError("LLM_TIMEOUT_SECONDS 必须是 1～120 的有限秒数。") from None
    return LLMConfig(
        api_key=SecretStr(values.get("LLM_API_KEY", "").strip()),
        base_url=values.get("LLM_BASE_URL", ""),
        model=values.get("LLM_MODEL", ""),
        supports_vision=vision == "true",
        timeout_seconds=timeout,
    )
