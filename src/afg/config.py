"""全局配置：密钥与可调参数统一从环境 / .env 读取，代码内禁止裸写。"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM 接入配置（OpenAI 兼容协议，默认指向 DeepSeek 官方端点）。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str = Field(validation_alias="DEEPSEEK_API_KEY")
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"
    temperature: float = 0.7