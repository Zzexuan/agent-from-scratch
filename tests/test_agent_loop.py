import pytest

from afg.agents.core import AgentCore
from afg.config import AgentConfig
from afg.context.messages import ToolCall
from afg.exceptions import AfgError
from afg.llm.base import LLMResponse
from afg.memory.sqlite import SQLiteMemory
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry
from tests.fakes import FakeLLM


def make_agent(responses, max_iterations=10, same_action_limit=3):
    fake = FakeLLM(responses)
    config = AgentConfig(
        max_iterations=max_iterations,
        same_action_limit=same_action_limit,
        retry_times=1,
    )
    agent = AgentCore(llm=fake, config=config)

    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    registry.register(get_weather)
    agent.register(registry)

    return agent, fake


def test_three_step_tool_chain_returns_final_answer():
    responses = [
        LLMResponse(
            content="先算数",
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expr": "12*34"})],
        ),
        LLMResponse(
            content="再查天气",
            tool_calls=[ToolCall(id="c2", name="get_weather", arguments={"city": "北京"})],
        ),
        LLMResponse(
            content="最后查时间",
            tool_calls=[ToolCall(id="c3", name="get_current_time", arguments={})],
        ),
        LLMResponse(content="12*34=408，北京晴，现在是 10:20:30"),
    ]
    agent, fake = make_agent(responses)

    answer = agent.run("先算 12*34，再查北京天气，最后告诉我现在几点")

    assert answer == "12*34=408，北京晴，现在是 10:20:30"
    assert len(fake.calls) == 4

    final_seen = fake.calls[3]
    assert len(final_seen) == 8
    assert final_seen[0].role == "system"
    assert final_seen[1].role == "user"
    assert final_seen[2].tool_calls[0].name == "calculator"
    assert final_seen[3].role == "tool"
    assert final_seen[3].tool_call_id == "c1"
    assert final_seen[3].content == "408"
    assert final_seen[4].tool_calls[0].name == "get_weather"
    assert final_seen[5].tool_call_id == "c2"
    assert final_seen[6].tool_calls[0].name == "get_current_time"
    assert final_seen[7].tool_call_id == "c3"


def test_repeated_action_triggers_circuit_break():
    same = LLMResponse(
        content="我再算一次",
        tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expr": "1+1"})],
    )
    responses = [same, same, same, LLMResponse(content="好吧，1+1 等于 2")]
    agent, fake = make_agent(responses, same_action_limit=3)

    answer = agent.run("一直算 1+1")

    assert answer == "好吧，1+1 等于 2"
    assert len(fake.calls) == 4

    last_seen = fake.calls[3]
    assert last_seen[-1].role == "user"
    assert "连续 3 次" in last_seen[-1].content
    assert fake.tool_schemas[3] is None


def test_max_iterations_triggers_circuit_break():
    responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={"expr": "1+1"})],
        ),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c2", name="calculator", arguments={"expr": "2+2"})],
        ),
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c3", name="calculator", arguments={"expr": "3+3"})],
        ),
        LLMResponse(content="三个都算完了：2、4、6"),
    ]
    agent, fake = make_agent(responses, max_iterations=3, same_action_limit=99)

    answer = agent.run("把三个式子都算一遍")

    assert answer == "三个都算完了：2、4、6"
    assert len(fake.calls) == 4
    assert "用完了全部 3 步" in fake.calls[3][-1].content
    assert fake.tool_schemas[3] is None


def test_unknown_tool_is_fed_back_to_model():
    responses = [
        LLMResponse(
            content="我来删",
            tool_calls=[ToolCall(id="c1", name="delete_file", arguments={"path": "a.txt"})],
        ),
        LLMResponse(content="抱歉，我没有删除文件的工具"),
    ]
    agent, fake = make_agent(responses)

    answer = agent.run("删掉 a.txt")

    assert answer == "抱歉，我没有删除文件的工具"
    seen = fake.calls[1]
    assert seen[3].role == "tool"
    assert seen[3].tool_call_id == "c1"
    assert "工具执行失败" in seen[3].content


def test_tool_argument_error_is_fed_back_to_model():
    responses = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="calculator", arguments={})],
        ),
        LLMResponse(content="我漏传参数了"),
    ]
    agent, fake = make_agent(responses)

    agent.run("帮我算一下")

    seen = fake.calls[1]
    assert "缺少必填参数 expr" in seen[3].content


def test_verbose_run_returns_answer():
    agent, fake = make_agent([LLMResponse(content="你好呀")])

    assert agent.run("你好", verbose=True) == "你好呀"
    assert len(fake.calls) == 1


def test_register_returns_self_for_chaining():
    agent, _ = make_agent([])
    registry = ToolRegistry()
    registry.register(calculator)

    assert agent.register(registry) is agent


def test_register_rejects_unknown_capability():
    agent, _ = make_agent([])

    with pytest.raises(AfgError):
        agent.register("我不是工具注册器")


def test_tools_returns_registered_tool_objects():
    agent, _ = make_agent([])

    names = []
    for tool in agent.tools():
        names.append(tool.name)

    assert names == ["calculator", "get_current_time", "get_weather"]


def test_memory_saves_only_fresh_messages():
    memory = SQLiteMemory(":memory:", session_id="test")
    responses = [LLMResponse(content="你好呀"), LLMResponse(content="好的")]
    agent, _ = make_agent(responses)
    agent.register(memory)

    agent.run("我叫小明")
    assert len(memory.load_context(k=99)) == 2

    agent.run("再说一遍")
    assert len(memory.load_context(k=99)) == 4


def test_memory_injects_history_into_next_run():
    memory = SQLiteMemory(":memory:", session_id="test")
    first_agent, _ = make_agent([LLMResponse(content="你好呀")])
    first_agent.register(memory)
    first_agent.run("我叫小明")

    second_agent, second_fake = make_agent([LLMResponse(content="你叫小明")])
    second_agent.register(memory)
    second_agent.run("我叫什么？")

    seen = second_fake.calls[0]
    assert seen[0].role == "system"
    assert seen[1].content == "我叫小明"
    assert seen[2].content == "你好呀"
    assert seen[3].content == "我叫什么？"
