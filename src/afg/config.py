"""全局配置：密钥与可调参数统一从环境 / .env 读取，代码内禁止裸写。

新手阅读顺序：
1. 先读类顶部的 model_config 行注释（理解"配置从哪来"）。
2. 再读一个字段（如 api_key）理解"字段 ← 环境变量"的映射。
3. 其余字段同理。看完你就明白为什么代码里从不出现真实密钥。

为什么配置要单独放一个文件、从环境变量读，而不是直接写在代码里：
① 密钥写进代码会进 git 仓库 → 泄露（面试必问的安全意识）；
② 模型名/温度/预算这类参数以后要调，集中在一处改比满代码找强；
③ .env 进 .gitignore 不提交，别人 clone 后按 .env.example 自己填。
"""

# pydantic-settings：pydantic 的"读环境变量"扩展。它让"类字段"自动从
# 环境变量 / .env 文件取值——你在 .env 写 DEEPSEEK_API_KEY=xxx，
# 构造 LLMConfig() 时字段就自动被填上，代码里不出现密钥本身。
# BaseSettings 就是"会自动读环境变量的 BaseModel"。
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM 接入配置（OpenAI 兼容协议，默认指向 DeepSeek 官方端点）。"""

    # model_config 是 pydantic 的"类级配置"，SettingsConfigDict(...) 里：
    #   env_file=".env"   → 启动时去当前目录找 .env 文件读取变量
    #   extra="ignore"    → 环境里多出来的无关变量直接忽略，不报错
    # 这行不用每处都懂，记住"配置来自 .env + 环境变量"即可。
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # validation_alias="DEEPSEEK_API_KEY"：把【字段名 api_key】映射到
    # 【环境变量名 DEEPSEEK_API_KEY】。为什么名字不一样：Python 命名习惯
    # 是下划线小写(api_key)，而环境变量惯例是全大写——alias 就是两者
    # 之间的翻译官。不写 alias 时 pydantic 默认找同名变量（如 MODEL）。
    api_key: str = Field(validation_alias="DEEPSEEK_API_KEY")
    base_url: str = "https://api.deepseek.com"  # DeepSeek 官方 OpenAI 兼容端点
    model: str = "deepseek-chat"  # DeepSeek 的对话模型名（V3 系列）
    temperature: float = 0.7  # 采样温度（默认 0.7，可在 .env 覆盖）


class ContextConfig(BaseSettings):
    """上下文预算配置（D2）：窗口/安全系数/压缩阈值，代码内禁止裸写数字。"""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    context_window_tokens: int = 8192  # 模型上下文窗口（deepseek-chat 实际更大，按需调小便于观察）
    safety_ratio: float = 0.75  # 预算 = 窗口 × 安全系数（窗口是"成本旋钮"，留余量给输出）
    compress_threshold: float = 0.75  # 使用率达到该比例触发压缩/告警（D3 压缩器复用）