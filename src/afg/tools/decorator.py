import inspect
import time

from afg.exceptions import ToolError
from afg.observability.logging import get_logger
from afg.tools.base import BaseTool

TYPE_TO_JSON = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
}


def first_paragraph(docstring):
    if not docstring:
        return ""
    lines = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if not stripped:
            break
        lines.append(stripped)
    return "\n".join(lines)


def parse_param_descriptions(docstring):
    descriptions = {}
    if not docstring:
        return descriptions
    for line in docstring.splitlines():
        stripped = line.strip()
        if not stripped.startswith(":param "):
            continue
        rest = stripped[len(":param ") :]
        if ":" not in rest:
            continue
        parts = rest.split(":", 1)
        descriptions[parts[0].strip()] = parts[1].strip()
    return descriptions


def build_parameters(fn):
    signature = inspect.signature(fn)
    descriptions = parse_param_descriptions(fn.__doc__)
    properties = {}
    required = []
    for name, param in signature.parameters.items():
        json_type = TYPE_TO_JSON.get(param.annotation)
        if json_type is None:
            raise TypeError(
                "工具 " + fn.__name__ + " 的参数 " + name + " 缺少类型注解或类型不支持："
                + repr(param.annotation)
            )
        info = {"type": json_type}
        if name in descriptions:
            info["description"] = descriptions[name]
        properties[name] = info
        if param.default is inspect.Parameter.empty:
            required.append(name)
    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def type_matches(expected, value):
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        if isinstance(value, bool):
            return False
        return isinstance(value, int)
    if expected == "number":
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float))
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "array":
        return isinstance(value, list)
    return True


def check_arguments(schema, kwargs):
    properties = schema["properties"]
    required = schema.get("required", [])
    for name in required:
        if name not in kwargs:
            return "缺少必填参数 " + name
    for name in kwargs:
        if name not in properties:
            available = "、".join(properties.keys())
            return "不支持参数 " + name + "，可用参数：" + available
        expected = properties[name]["type"]
        if not type_matches(expected, kwargs[name]):
            return "参数 " + name + " 类型不对，应该是 " + expected
    return ""


class FunctionTool(BaseTool):
    def __init__(self, fn, name, description, schema):
        self._fn = fn
        self.name = name
        self.description = description
        self._schema = schema

    def parameters(self):
        return self._schema

    def run(self, **kwargs):
        problem = check_arguments(self._schema, kwargs)
        if problem:
            raise ToolError(
                "参数错误：" + problem,
                context={"tool": self.name, "arguments": kwargs},
            )

        logger = get_logger("tool")
        started = time.perf_counter()
        result = str(self._fn(**kwargs))
        logger.info(
            "tool.call",
            name=self.name,
            params=kwargs,
            result_length=len(result),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return result


def tool(fn):
    description = first_paragraph(fn.__doc__)
    if not description:
        raise TypeError("工具 " + fn.__name__ + " 缺少 docstring，没法生成 description")
    schema = build_parameters(fn)
    return FunctionTool(fn, fn.__name__, description, schema)
