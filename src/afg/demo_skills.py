from afg.agents.core import AgentCore
from afg.config import AgentConfig, LLMConfig, SkillConfig
from afg.llm.deepseek_client import DeepSeekClient
from afg.observability.logging import get_logger, setup_logging
from afg.skills.base import SkillLoader, load_skill
from afg.tools.registry import ToolRegistry

BAD_CODE = '''
def get_user(id):
    """取用户"""
    data = open("users.txt").read().split("\\n")
    for row in data:
        if row.split(",")[0] == id:
            return row.split(",")[1]
    return None
'''

REVIEW_TASK = "帮我审查下面这段代码有没有问题：\n" + BAD_CODE
PLAIN_TASK = "用一句话解释什么是上下文窗口"


def build_registry():
    registry = ToolRegistry()
    registry.register(load_skill)
    return registry


def main():
    setup_logging()
    logger = get_logger("demo_skills")
    config = SkillConfig()

    loader = SkillLoader(config.skills_dir)
    agent = AgentCore(llm=DeepSeekClient(LLMConfig()), config=AgentConfig())
    agent.register(loader)
    agent.register(build_registry())

    logger.info("demo_skills.start", skills=loader.names())

    review = agent.run(REVIEW_TASK)
    logger.info("demo_skills.review", answer=review)

    plain = agent.run(PLAIN_TASK)
    logger.info("demo_skills.plain", answer=plain)


if __name__ == "__main__":
    main()
