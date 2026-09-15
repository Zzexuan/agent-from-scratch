from afg.exceptions import DuplicateToolError, UnknownToolError
from afg.tools.base import to_openai_schema


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, tool):
        if tool.name in self._tools:
            raise DuplicateToolError("工具名重复，已经注册过了", context={"tool": tool.name})
        self._tools[tool.name] = tool

    def get(self, name):
        if name not in self._tools:
            raise UnknownToolError(
                "没有这个工具",
                context={"tool": name, "available": list(self._tools.keys())},
            )
        return self._tools[name]

    def names(self):
        return list(self._tools.keys())

    def to_openai_schemas(self):
        schemas = []
        for tool in self._tools.values():
            schemas.append(to_openai_schema(tool))
        return schemas
