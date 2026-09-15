import sys
import time

from afg.config import LLMConfig
from afg.context.messages import Message
from afg.exceptions import AfgError
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry

DEFAULT_QUESTION = "帮我算 37*89"


def build_registry():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    return registry


def main(question):
    setup_logging()
    logger = get_logger("demo_fc")
    config = LLMConfig()
    llm = DeepSeekClient(config)

    registry = build_registry()
    schemas = registry.to_openai_schemas()

    logger.info("fc.start", question=question, tools=registry.names())

    messages = [Message(role="user", content=question)]

    started = time.perf_counter()
    resp = llm.chat(messages, tools=schemas)
    logger.info(
        "fc.llm_call",
        call=1,
        messages=len(messages),
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )

    if not resp.tool_calls:
        logger.info("fc.no_tool_call", content=resp.content)
        return

    messages.append(Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls))

    for tc in resp.tool_calls:
        logger.info("fc.tool_request", tool=tc.name, arguments=tc.arguments, call_id=tc.id)

        started_tool = time.perf_counter()
        try:
            tool = registry.get(tc.name)
            result = tool.run(**tc.arguments)
        except AfgError as e:
            result = "工具执行失败：" + str(e)
            logger.warning("fc.tool_error", tool=tc.name, error=str(e), context=e.context)

        logger.info(
            "fc.tool_call",
            tool=tc.name,
            arguments=tc.arguments,
            result_length=len(result),
            latency_ms=round((time.perf_counter() - started_tool) * 1000, 1),
        )
        messages.append(Message(role="tool", content=result, tool_call_id=tc.id))

    started = time.perf_counter()
    final = llm.chat(messages, tools=schemas)
    logger.info(
        "fc.llm_call",
        call=2,
        messages=len(messages),
        prompt_tokens=final.usage.prompt_tokens,
        completion_tokens=final.usage.completion_tokens,
        latency_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    logger.info("fc.final_answer", content=final.content)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main(DEFAULT_QUESTION)
