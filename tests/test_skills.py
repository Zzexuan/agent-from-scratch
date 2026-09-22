import pytest

from afg.agents.core import SYSTEM_PROMPT, AgentCore
from afg.config import AgentConfig
from afg.exceptions import AfgError, ToolError
from afg.llm.base import LLMResponse
from afg.skills.base import SkillLoader, load_skill, read_skill_file
from tests.fakes import FakeLLM

SKILL_ALPHA = """---
name: alpha
description: 处理甲类任务，口径见 https://example.com/doc
---

# 甲手册

甲的第一步。
甲的第二步。
"""

SKILL_BETA = """---
name: beta
description: 处理乙类任务
---

# 乙手册

乙的正文。
"""

SKILL_NO_DESCRIPTION = """---
name: gamma
---

# 丙手册

丙的正文。
"""


def write_skill(directory, file_name, text):
    path = directory / file_name
    path.write_text(text, encoding="utf-8")
    return path


def make_loader(tmp_path):
    write_skill(tmp_path, "alpha.md", SKILL_ALPHA)
    write_skill(tmp_path, "beta.md", SKILL_BETA)
    return SkillLoader(str(tmp_path))


def make_agent(responses):
    fake = FakeLLM(responses)
    agent = AgentCore(llm=fake, config=AgentConfig(retry_times=1))
    return agent, fake


def test_description_keeps_ascii_colon_intact(tmp_path):
    path = write_skill(tmp_path, "alpha.md", SKILL_ALPHA)

    name, description, _ = read_skill_file(str(path))

    assert name == "alpha"
    assert description == "处理甲类任务，口径见 https://example.com/doc"


def test_missing_description_raises(tmp_path):
    path = write_skill(tmp_path, "gamma.md", SKILL_NO_DESCRIPTION)

    with pytest.raises(AfgError):
        read_skill_file(str(path))


def test_scan_collects_every_markdown_skill(tmp_path):
    loader = make_loader(tmp_path)

    assert loader.names() == ["alpha", "beta"]
    assert len(loader.list_skills()) == 2


def test_index_keeps_only_name_and_description(tmp_path):
    loader = make_loader(tmp_path)

    index = loader.inject_index()

    assert "alpha" in index
    assert "beta" in index
    assert "处理甲类任务" in index
    assert "load_skill" in index
    assert "甲的第一步" not in index


def test_load_body_drops_frontmatter(tmp_path):
    loader = make_loader(tmp_path)

    body = loader.load_body("alpha")

    assert body.startswith("# 甲手册")
    assert "甲的第一步" in body
    assert "description" not in body
    assert "---" not in body


def test_load_skill_tool_rejects_unknown_name():
    with pytest.raises(ToolError):
        load_skill.run(name="不存在的技能")


def test_run_injects_skill_index_into_system_message(tmp_path):
    loader = make_loader(tmp_path)
    agent, fake = make_agent([LLMResponse(content="好的")])
    agent.register(loader)

    agent.run("随便问一句")

    system = fake.calls[0][0]
    assert system.role == "system"
    assert "alpha" in system.content
    assert "处理甲类任务" in system.content
    assert "load_skill" in system.content
    assert "甲的第一步" not in system.content


def test_run_without_loader_keeps_plain_system_prompt():
    agent, fake = make_agent([LLMResponse(content="好的")])

    agent.run("随便问一句")

    assert fake.calls[0][0].content == SYSTEM_PROMPT
