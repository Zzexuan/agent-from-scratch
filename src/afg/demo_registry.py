import json

from afg.config import LLMConfig
from afg.context.messages import Message, ToolCall
from afg.exceptions import UnknownToolError
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry

HALLUCINATED_TOOL = "delete_file"


def build_registry():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    return registry


def show_schemas(logger, registry):
    schemas = registry.to_openai_schemas()
    for schema in schemas:
        logger.info(
            "registry.schema",
            tool=schema["function"]["name"],
            schema=json.dumps(schema, ensure_ascii=False),
        )


def main():
    setup_logging()
    logger = get_logger("demo_registry")
    registry = build_registry()

    logger.info("registry.start", tools=registry.names())
    show_schemas(logger, registry)

    hallucinated = ToolCall(id="call_fake_1", name=HALLUCINATED_TOOL, arguments={"path": "a.txt"})
    logger.info("registry.hallucination", tool=hallucinated.name, call_id=hallucinated.id)

    try:
        registry.get(hallucinated.name)
        result = "（不该走到这里：注册器竟然找到了这个工具）"
    except UnknownToolError as e:
        result = "工具不存在：" + hallucinated.name
        result += "。可用工具：" + "、".join(e.context["available"])
        logger.warning("registry.unknown_tool", tool=hallucinated.name, message=result)

    config = LLMConfig()
    llm = DeepSeekClient(config)
    messages = [
        Message(role="user", content="帮我用 " + HALLUCINATED_TOOL + " 工具删掉 a.txt"),
        Message(role="assistant", content=None, tool_calls=[hallucinated]),
        Message(role="tool", content=result, tool_call_id=hallucinated.id),
    ]

    resp = llm.chat(messages, tools=registry.to_openai_schemas())
    logger.info(
        "registry.recovered",
        prompt_tokens=resp.usage.prompt_tokens,
        completion_tokens=resp.usage.completion_tokens,
        content=resp.content,
    )


if __name__ == "__main__":
    main()
