class AfgError(Exception):
    def __init__(self, message, context=None):
        # 例外语法：super() 已获同意（见 agent-learning/代码写法约束.md）
        super().__init__(message)
        if context is None:
            context = {}
        self.context = context


class LLMTimeoutError(AfgError):
    pass


class ToolError(AfgError):
    pass


class ContextOverflowError(AfgError):
    pass


class UnknownToolError(AfgError):
    pass


class DuplicateToolError(AfgError):
    pass
