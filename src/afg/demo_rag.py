from afg.agents.core import AgentCore
from afg.config import AgentConfig, LLMConfig
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry
from afg.tools.search_notes import search_notes

QUESTION = "帮我找一下我哪篇笔记讲过 function calling 的四步流程"


def build_registry():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    registry.register(search_notes)
    return registry


def main():
    setup_logging()
    logger = get_logger("demo_rag")
    agent = AgentCore(llm=DeepSeekClient(LLMConfig()), config=AgentConfig())
    agent.register(build_registry())

    logger.info("demo_rag.start", question=QUESTION)
    answer = agent.run(QUESTION)
    logger.info("demo_rag.answer", question=QUESTION, answer=answer)


if __name__ == "__main__":
    main()
