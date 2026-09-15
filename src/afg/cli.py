from afg.agents.core import AgentCore
from afg.config import AgentConfig, LLMConfig
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry

HELP_TEXT = "命令：/tools 列出工具  /trace 开关逐步显示  /exit 退出"


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    return registry


def main() -> None:
    setup_logging()
    logger = get_logger("cli")

    agent = AgentCore(llm=DeepSeekClient(LLMConfig()), config=AgentConfig())
    agent.register(build_registry())

    logger.info("cli.start", hint=HELP_TEXT)

    show_trace = False
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text in ("/exit", "/quit"):
            break
        if text == "/tools":
            for tool in agent.tools():
                logger.info("cli.tool", name=tool.name, description=tool.description)
            continue
        if text == "/trace":
            show_trace = not show_trace
            logger.info("cli.trace", enabled=show_trace)
            continue

        answer = agent.run(text, verbose=show_trace)
        logger.info("cli.answer", content=answer)


if __name__ == "__main__":
    main()
