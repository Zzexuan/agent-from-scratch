from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = Field(validation_alias="DEEPSEEK_API_KEY")
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.7


class ContextConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    context_window_tokens: int = 8192
    safety_ratio: float = 0.75
    compress_threshold: float = 0.75
    compress_keep_recent: int = 20
    compress_target_ratio: float = 0.375


class AgentConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    max_iterations: int = 10
    same_action_limit: int = 3
    retry_times: int = 3
    retry_backoff: float = 1.5
