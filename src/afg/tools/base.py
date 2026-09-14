from abc import ABC, abstractmethod


class BaseTool(ABC):
    name = ""
    description = ""

    @abstractmethod
    def parameters(self):
        ...

    @abstractmethod
    def run(self, **kwargs):
        ...


def to_openai_schema(tool):
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters(),
        },
    }
