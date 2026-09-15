import pytest

from afg.exceptions import DuplicateToolError, UnknownToolError
from afg.tools.builtin import calculator, get_current_time, get_weather
from afg.tools.registry import ToolRegistry


def make_registry():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_current_time)
    return registry


def test_register_and_get():
    registry = make_registry()
    tool = registry.get("calculator")
    assert tool.name == "calculator"
    assert tool.run(expr="1+1") == "2"


def test_names_lists_registered_tools():
    registry = make_registry()
    assert registry.names() == ["calculator", "get_current_time"]


def test_duplicate_name_raises():
    registry = make_registry()
    with pytest.raises(DuplicateToolError) as info:
        registry.register(calculator)
    assert info.value.context["tool"] == "calculator"


def test_unknown_tool_raises_with_available_list():
    registry = make_registry()
    with pytest.raises(UnknownToolError) as info:
        registry.get("delete_file")
    assert info.value.context["tool"] == "delete_file"
    assert "calculator" in info.value.context["available"]


def test_to_openai_schemas_shape():
    registry = ToolRegistry()
    registry.register(calculator)
    registry.register(get_weather)

    schemas = registry.to_openai_schemas()

    assert len(schemas) == 2
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "calculator"
    assert schemas[1]["function"]["name"] == "get_weather"
    assert schemas[1]["function"]["parameters"]["required"] == ["city"]


def test_empty_registry_gives_empty_schemas():
    registry = ToolRegistry()
    assert registry.names() == []
    assert registry.to_openai_schemas() == []
