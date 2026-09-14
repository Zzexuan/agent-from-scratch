import sys
import time

from afg.config import LLMConfig
from afg.context.messages import Message
from afg.exceptions import ToolError, UnknownToolError
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.tools.base import to_openai_schema
from afg.tools.builtin import CalculatorTool, CurrentTimeTool, WeatherTool

DEFAULT_QUESTION = "帮我算 37*89"


def find_tool(tools, name):
    for tool in tools:
        if tool.name == name:
            return tool
    raise UnknownToolError("模型要求调用一个不存在的工具", context={"tool": name})


def main(question):
    setup_logging()
    logger = get_logger("demo_fc")
    config = LLMConfig()
    llm = DeepSeekClient(config)

    tools = [CalculatorTool(), CurrentTimeTool(), WeatherTool()]
    schemas = []
    for tool in tools:
        schemas.append(to_openai_schema(tool))

    logger.info("fc.start", question=question, tool_count=len(tools))

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
        tool = find_tool(tools, tc.name)

        started_tool = time.perf_counter()
        try:
            result = tool.run(**tc.arguments)
        except ToolError as e:
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
