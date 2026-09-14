"""消息模型：Agent 上下文的最小原子，也是与 OpenAI 兼容 API 之间转换的唯一入口。

D1 规格（主文档「核心接口规格」）：Role / ToolCall / Message / TokenUsage。
D4 起 tools 模块将依赖这里的 ToolCall 解析结果。

新手阅读顺序：
1. 先看 TokenUsage 类（最简单，只有两个数字字段）。
2. 再看 ToolCall 类（工具调用指令）。
3. 最后看 Message 类（本文件核心）——这里集中了 pydantic
   的进阶语法，每处都配了注释，遇到 `|` / `= None` / @model_validator
   看不懂就停在这文件里找注释，不要跳过去。
"""

# 本文件第一次出现类型别名与类型注解，先建立两个基础认知：
#
# 【认知 1：类型注解是什么】
#   Python 本身不在乎变量是 int 还是 str（它运行时才看值），
#   但我们可以"用注解告诉读代码的人（和工具）这个值应该是啥类型"：
#       name: str = "小明"    # 冒号后面是类型注解，不改变程序行为
#   它对运行没影响，但能：让编辑器自动提示补全、让 ruff/mypy 静态查错、
#   让你（读者）不用猜这个变量到底是什么。本项目要求每个函数/字段都写。
#
# 【认知 2：为什么用 pydantic 的 BaseModel 而不是普通 class】
#   普通 class 的字段"没人管"——你写 message.content = 123 也不会报错；
#   BaseModel 则会在赋值/构造时自动做三件事：
#     ① 类型校验：传错类型立刻报错（比如 role 传了数字）；
#     ② 类型转换：传 dict 进去会自动变成 ToolCall 对象（tests 里会看到）；
#     ③ 序列化：一行 model_dump() 把对象变成 dict/JSON，方便发给 API。
#   聊天消息是要发给外部 API 的"协议数据"，校验严格 = 少踩坑，所以用 pydantic。

from typing import Any, Literal

from pydantic import BaseModel, model_validator

# Literal["system", "user", "assistant", "tool"] 意思是：
# "这个字段只允许取这 4 个字符串值之一"。把"角色"限定成固定几种，
# 防止手滑写成 "userr" 之类——OpenAI 协议只认这 4 种，写错 API 会 400。
# Role 不是类而是"类型别名"：给一长串类型注解起个短名字，之后写
# `role: Role` 等价于写 `role: Literal["system", "user", "assistant", "tool"]`。
Role = Literal["system", "user", "assistant", "tool"]


class ToolCall(BaseModel):
    """LLM 返回的一次结构化工具调用指令。

    生活类比：老板（LLM）不开会口述，而是写一张"派工单"：
    单号(id)、派给谁(name)、要带什么材料(arguments)。
    运行时（员工）凭这张单子去执行，执行完把结果按单号回填。
    """

    id: str  # LLM 返回的 call id（单号，用于把"工具结果"和"这次调用"对上）
    name: str  # 工具名（派给谁：如 "calculator"）
    # dict[str, Any] = "键是 str、值是任意类型"的字典（材料清单，已解析成 Python 对象）
    # 注意：API 原始返回的 arguments 是 JSON 字符串，解析发生在 llm 层（见 deepseek_client.py）
    arguments: dict[str, Any]


class Message(BaseModel):
    """一条对话消息，直接对应 OpenAI 协议 messages 数组里的一个元素。

    一段对话 = 多条 Message 按顺序排成的列表（messages）。
    每条消息有：谁说的(role) + 说了什么(content)；
    当角色是 assistant 且它想调工具时，不说人话而是给 tool_calls；
    当角色是 tool 时，content 是工具执行结果，并要带 tool_call_id 指明
    "我回答的是哪张派工单"。
    """

    # 下面的 `str | None = None` 是新手最容易懵的写法，逐步拆解：
    #   content: str | None = None
    #   └字段名  └──类型──┘  └默认值
    # ① "str | None" 读作"str 或 None"：这个字段可以是文本，也可以是"没有"。
    # ② "= None" 是默认值：构造 Message 时不传 content 也行，自动填 None。
    # ③ 为什么要"可为空"：assistant 消息一旦带工具调用(tool_calls)，
    #    它就没有普通文本回复，content 只能是空——所以"有没有文本"是可选
    #    的。同理 role=tool 的消息只装工具结果，没有"对话文本"。
    # ④ 这正是 pydantic 帮我们的：字段可填可不填，类型错了它立刻报错。
    role: Role
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # role=assistant 可有；list[X] = "X 的列表"
    tool_call_id: str | None = None  # role=tool 时必填（回答哪张派工单）

    # @model_validator(mode="after") 是 pydantic 提供的"钩子"装饰器：
    # 它让下面这个方法在【每条 Message 构造完成之后】自动被调用一次，
    # 用来做"单个字段校验做不到"的【跨字段】检查。
    # 语法速记：@xxx 叫装饰器 = "给函数附加额外行为"，这里的行为是
    # "对象建好后先跑一遍这个检查函数"。mode="after" = 在字段都填好之后。
    @model_validator(mode="after")
    def _check_role_tool(self) -> "Message":
        """role=tool 必须带 tool_call_id，否则 DeepSeek 侧会 400（新手第一大坑）。

        为什么会有这个坑：API 收到 role=tool 却不知道它回答哪次调用，
        就拼不上"助手派单 → 工具回单"的链条，直接拒绝请求。
        与其等到 API 报错，不如在我们这边构造时就拦住——pydantic 校验
        抛出的 ValueError 会立刻暴露问题在哪一行。
        """
        # 注意返回注解写 "Message" 带引号：方法定义时 Message 类还没完全
        # 建好，Python 不允许"引用还没定义完的类名"，加引号变成字符串
        # 就只是"给读者的说明"，延迟到运行时才解析。这叫 forward reference。
        if self.role == "tool" and not self.tool_call_id:
            # raise = 主动抛异常；ValueError 表示"值不合法"。
            # 抛出后这条 Message 构造失败，调用方必须处理，防止坏数据往下游走。
            raise ValueError("role='tool' 的消息必须带 tool_call_id")
        return self


class TokenUsage(BaseModel):
    """单次响应的 token 用量统计。

    token = 模型处理文本的最小单位（大概相当于"半个词/一个汉字"的量级）。
    API 每次响应都会告诉我们这轮花了多少 token，记下来用于成本核算。
    """

    # int = 0：字段是整数，不传时默认 0（API 没返回 usage 时兜底，见 llm 层）。
    prompt_tokens: int = 0  # 你发过去的消息（输入）消耗的 token
    completion_tokens: int = 0  # 模型回复（输出）消耗的 token

    # @property 装饰器：把方法伪装成"普通属性"，调用时不用加括号。
    # 用法：usage.total  （不是 usage.total()）
    # 好处：外部读起来像字段，但值是实时算出来的——total 永远 = 两者之和，
    # 不会出现"有人改了 prompt_tokens 却忘了改 total"的失同步 bug。
    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens