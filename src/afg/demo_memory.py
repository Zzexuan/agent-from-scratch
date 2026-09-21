import sys

from afg.agents.core import AgentCore
from afg.config import AgentConfig, LLMConfig, MemoryConfig
from afg.llm.deepseek_client import DeepSeekClient
from afg.memory.sqlite import SQLiteMemory
from afg.observability.logging import get_logger, setup_logging

DEFAULT_QUESTION = "我叫小明，请记住这个名字"


def main(question):
    setup_logging()
    logger = get_logger("demo_memory")
    config = MemoryConfig()

    memory = SQLiteMemory(config.db_path(), session_id=config.session_id)
    agent = AgentCore(llm=DeepSeekClient(LLMConfig()), config=AgentConfig())
    agent.register(memory)

    answer = agent.run(question)
    logger.info("demo_memory.answer", question=question, answer=answer)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main(DEFAULT_QUESTION)
