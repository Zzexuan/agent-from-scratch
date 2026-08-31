"""多轮对话 CLI：`python -m afg.chat`

D1 手搓核心体验 —— **上下文 = 你自己维护的 messages 列表**。
每一轮：append user → llm.chat(messages) → 打印 → append assistant。
D1 允许 print（structlog 从 D2 接入）。
"""

from afg.config import LLMConfig
from afg.context.messages import Message
from afg.llm.deepseek_client import DeepSeekClient

SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用简体中文回答。"


def main() -> None:
    config = LLMConfig()
    llm = DeepSeekClient(config)
    messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]

    print(f"[模型 {config.model} | 端点 {config.base_url}] 输入 exit/quit 结束")
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        messages.append(Message(role="user", content=text))
        resp = llm.chat(messages)
        print(f"AI > {resp.content}")
        messages.append(Message(role="assistant", content=resp.content))


if __name__ == "__main__":
    main()