from afg import AgentConfig, AgentCore, DeepSeekClient, LLMConfig, ToolRegistry
from afg.observability.logging import get_logger, setup_logging
from afg.tools.builtin import calculator, get_current_time, get_weather

TASK = "帮我算 12*34"


def registry_only_calculator():
    registry = ToolRegistry()
    registry.register(calculator)
    return registry


def registry_all_tools():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    return registry


def main():
    setup_logging()
    logger = get_logger("demo_hotswap")

    agent = AgentCore(llm=DeepSeekClient(LLMConfig()), config=AgentConfig())

    agent.register(registry_only_calculator())
    logger.info("hotswap.round", round=1, tools=agent.registry_names())
    first = agent.run(TASK)
    logger.info("hotswap.answer", round=1, answer=first)

    agent.register(registry_all_tools())
    logger.info("hotswap.round", round=2, tools=agent.registry_names())
    second = agent.run(TASK)
    logger.info("hotswap.answer", round=2, answer=second)


if __name__ == "__main__":
    main()
