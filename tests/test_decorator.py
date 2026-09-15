import pytest

from afg.exceptions import ToolError
from afg.tools.decorator import tool


@tool
def add_numbers(a: int, b: int = 0) -> int:
    """把两个数相加。

    :param a: 第一个加数
    :param b: 第二个加数，可以不传，默认 0
    """
    return a + b


@tool
def all_types(text: str, count: int, ratio: float, flag: bool, items: list) -> str:
    """演示五种参数类型。

    :param text: 字符串参数
    :param count: 整数参数
    :param ratio: 浮点参数
    :param flag: 布尔参数
    :param items: 列表参数
    """
    return text


def unsupported_type(value: dict) -> str:
    """参数类型不在支持范围内的工具。"""
    return ""


def no_docstring(value: str) -> str:
    return ""


def test_schema_type_mapping():
    properties = all_types.parameters()["properties"]
    assert properties["text"]["type"] == "string"
    assert properties["count"]["type"] == "integer"
    assert properties["ratio"]["type"] == "number"
    assert properties["flag"]["type"] == "boolean"
    assert properties["items"]["type"] == "array"


def test_required_inference():
    schema = add_numbers.parameters()
    assert schema["required"] == ["a"]


def test_docstring_first_paragraph_becomes_description():
    assert add_numbers.description == "把两个数相加。"
    assert all_types.description == "演示五种参数类型。"


def test_param_description_parsed():
    properties = add_numbers.parameters()["properties"]
    assert properties["a"]["description"] == "第一个加数"
    assert properties["b"]["description"] == "第二个加数，可以不传，默认 0"


def test_tool_name_from_function_name():
    assert add_numbers.name == "add_numbers"
    assert all_types.name == "all_types"


def test_run_converts_result_to_string():
    result = add_numbers.run(a=1, b=2)
    assert result == "3"
    assert isinstance(result, str)


def test_missing_required_argument_raises():
    with pytest.raises(ToolError) as info:
        add_numbers.run(b=5)
    assert "缺少必填参数" in str(info.value)
    assert info.value.context["tool"] == "add_numbers"


def test_unexpected_argument_raises():
    with pytest.raises(ToolError) as info:
        add_numbers.run(a=1, c=9)
    assert "不支持参数" in str(info.value)


def test_wrong_type_raises():
    with pytest.raises(ToolError) as info:
        add_numbers.run(a="一")
    assert "类型不对" in str(info.value)


def test_bool_is_not_accepted_as_integer():
    with pytest.raises(ToolError):
        add_numbers.run(a=True)


def test_unsupported_type_annotation_raises():
    with pytest.raises(TypeError):
        tool(unsupported_type)


def test_missing_docstring_raises():
    with pytest.raises(TypeError):
        tool(no_docstring)
