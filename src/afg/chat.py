"""多轮对话 CLI：`python -m afg.chat`

D1 手搓核心体验 —— **上下文 = 你自己维护的 messages 列表**（append-only）。
D2 升级：每轮输出 token 统计（使用率 / 预算），≥75% 红色警告（只警告，D3 才接压缩）；
全部输出走 structlog（chat.turn / context.near_full / chat.reply 事件），禁止 print。
"""

import time

import structlog

from afg.config import ContextConfig, LLMConfig
from afg.context.counter import TokenCounter
from afg.context.messages import Message
from afg.context.window import ContextWindow
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging

SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用简体中文回答。"


def main() -> None:
    setup_logging()
    config = LLMConfig()
    ctx_cfg = ContextConfig()
    logger = get_logger("chat")
    llm = DeepSeekClient(config)
    counter = TokenCounter()
    window = ContextWindow.from_model(ctx_cfg.context_window_tokens, ctx_cfg.safety_ratio)
    messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]

    logger.info(
        "chat.session_start",
        model=config.model,
        base_url=config.base_url,
        budget=window.budget,
    )

    turn = 0
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            break

        turn += 1
        structlog.contextvars.bind_contextvars(step=turn)
        started = time.perf_counter()
        messages.append(Message(role="user", content=text))
        resp = llm.chat(messages)
        messages.append(Message(role="assistant", content=resp.content))
        latency_ms = (time.perf_counter() - started) * 1000

        report = window.check(messages, counter)
        usage_pct = round(report.usage_ratio * 100, 1)
        logger.info(
            "chat.turn",
            turn=turn,
            tokens=report.total_tokens,
            budget=report.budget,
            usage_pct=usage_pct,
            latency_ms=round(latency_ms, 1),
        )
        if report.should_compress:
            # D2 只警告不压缩；D3 起这里改调 Compressor
            logger.warning("context.near_full", usage_pct=usage_pct, threshold=75.0)
        logger.info("chat.reply", content=resp.content)


if __name__ == "__main__":
    main()