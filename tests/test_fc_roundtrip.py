import json

import pytest

from afg.context.messages import Message, ToolCall
from afg.exceptions import ToolError
from afg.llm.base import LLMResponse
from afg.llm.deepseek_client import to_api_message
from afg.tools.base import to_openai_schema
from afg.tools.builtin import CalculatorTool, CurrentTimeTool, WeatherTool
from tests.fakes import FakeLLM


def test_fc_message_order_roundtrip():
    tool_call = ToolCall(id="call_1", name="calculator", arguments={"expr": "37*89"})
    llm = FakeLLM(
        [
            LLMResponse(content=None, tool_calls=[tool_call]),
            LLMResponse(content="37*89 等于 3293"),
        ]
    )
    schemas = [to_openai_schema(CalculatorTool())]

    messages = [Message(role="user", content="帮我算 37*89")]
    first = llm.chat(messages, tools=schemas)
    messages.append(Message(role="assistant", content=first.content, tool_calls=first.tool_calls))

    result = CalculatorTool().run(**tool_call.arguments)
    messages.append(Message(role="tool", content=result, tool_call_id=tool_call.id))

    llm.chat(messages, tools=schemas)

    seen = llm.calls[1]
    assert len(seen) == 3
    assert seen[0].role == "user"
    assert seen[1].role == "assistant"
    assert seen[2].role == "tool"
    assert seen[1].tool_calls[0].id == seen[2].tool_call_id
    assert seen[2].content == "3293"
    assert llm.tool_schemas[0] == schemas


def test_calculator_basic():
    tool = CalculatorTool()
    assert tool.run(expr="37*89") == "3293"
    assert tool.run(expr="(1+2)*3") == "9"
    assert tool.run(expr="10/4") == "2.5"
    assert tool.run(expr="-5 + 8") == "3"
    assert tool.run(expr="2**10") == "1024"


def test_calculator_rejects_function_call():
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        tool.run(expr="__import__('os').system('dir')")


def test_calculator_rejects_variable_name():
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        tool.run(expr="a + 1")


def test_calculator_rejects_division_by_zero():
    tool = CalculatorTool()
    with pytest.raises(ToolError):
        tool.run(expr="1/0")


def test_weather_unknown_city_carries_context():
    tool = WeatherTool()
    with pytest.raises(ToolError) as info:
        tool.run(city="火星")
    assert info.value.context["city"] == "火星"


def test_current_time_tool_has_no_parameters():
    tool = CurrentTimeTool()
    assert tool.parameters()["properties"] == {}
    result = tool.run()
    assert len(result) == 19


def test_to_openai_schema_shape():
    schema = to_openai_schema(CalculatorTool())
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "calculator"
    assert schema["function"]["description"] != ""
    assert schema["function"]["parameters"]["type"] == "object"
    assert "expr" in schema["function"]["parameters"]["properties"]
    assert schema["function"]["parameters"]["required"] == ["expr"]


def test_tool_call_message_serializes_for_api():
    message = Message(
        role="assistant",
        content=None,
        tool_calls=[ToolCall(id="call_1", name="calculator", arguments={"expr": "37*89"})],
    )

    data = to_api_message(message)

    assert data["tool_calls"][0]["type"] == "function"
    assert data["tool_calls"][0]["function"]["name"] == "calculator"
    assert json.loads(data["tool_calls"][0]["function"]["arguments"]) == {"expr": "37*89"}


def test_plain_message_serializes_unchanged():
    message = Message(role="user", content="你好")

    data = to_api_message(message)

    assert data == {"role": "user", "content": "你好"}
