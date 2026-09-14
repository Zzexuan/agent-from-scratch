import time

import structlog

from afg.config import ContextConfig, LLMConfig
from afg.context.compressor import Compressor
from afg.context.counter import TokenCounter
from afg.context.messages import Message
from afg.context.window import ContextWindow
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging

SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用简体中文回答。"


def main():
    setup_logging()
    config = LLMConfig()
    ctx_cfg = ContextConfig()
    logger = get_logger("chat")
    llm = DeepSeekClient(config)
    counter = TokenCounter()
    window = ContextWindow.from_model(ctx_cfg.context_window_tokens, ctx_cfg.safety_ratio)
    compressor = Compressor(budget=window.budget, target_ratio=ctx_cfg.compress_target_ratio)

    messages = [Message(role="system", content=SYSTEM_PROMPT)]

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
            messages_before = len(messages)
            before_tokens = report.total_tokens
            started_compress = time.perf_counter()
            messages = compressor.compress(messages, llm, counter, ctx_cfg.compress_keep_recent)
            compress_ms = (time.perf_counter() - started_compress) * 1000
            after_report = window.check(messages, counter)
            logger.info(
                "context.compress",
                messages_before=messages_before,
                messages_after=len(messages),
                before_tokens=before_tokens,
                after_tokens=after_report.total_tokens,
                ratio=round(after_report.total_tokens / before_tokens, 3),
                compress_ms=round(compress_ms, 1),
            )
            if after_report.should_compress:
                logger.warning(
                    "context.still_full",
                    usage_pct=round(after_report.usage_ratio * 100, 1),
                )
        logger.info("chat.reply", content=resp.content)


if __name__ == "__main__":
    main()
