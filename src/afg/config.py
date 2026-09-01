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


class ContextConfig(BaseSettings):
    """上下文预算配置（D2）：窗口/安全系数/压缩阈值，代码内禁止裸写数字。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    context_window_tokens: int = 8192  # 模型上下文窗口（deepseek-chat 实际更大，按需调小便于观察）
    safety_ratio: float = 0.75  # 预算 = 窗口 × 安全系数（窗口是"成本旋钮"，留余量给输出）
    compress_threshold: float = 0.75  # 使用率达到该比例触发压缩/告警（D3 压缩器复用）