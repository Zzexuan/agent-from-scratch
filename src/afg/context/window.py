"""上下文窗口预算：把窗口当 RAM 做配额管理（D2 手搓规格）。

- `ContextWindow(budget)`：budget = 模型窗口 × 安全系数（默认 0.75），
  即"系统指令 + 工具 schema + 历史 + 输出余量"四个份额的总上限。
- `check()` 返回 `ContextReport`：使用率与是否该压缩（D3 压缩器只认 should_compress）。
- 使用率达到 75% 就预警：75% 触发、压到 37.5%（≈ 一半），对齐业界实践。

新手阅读顺序：
1. 先读 ContextWindow 类的两个方法（本文件核心）。
2. 再看 ContextReport 类（check 返回的"报告单"长什么样）。
3. 最后看 COMPRESS_THRESHOLD 常量（75% 从哪来）。
4. 生活类比：ContextWindow = 你的"内存条剩余量"；check() = 每隔一会儿
   看一眼任务管理器。内存快满了(RAM 类比)→ 该关后台程序了（D3 压缩）。
"""

# Field：pydantic 给字段附加"校验/默认值"的函数（首次出现见 base.py 注释）。
# 这里额外用到了 ge 约束（下面 ContextReport 里讲）。
from pydantic import BaseModel, Field

from afg.context.counter import TokenCounter
from afg.context.messages import Message

# 压缩触发阈值：使用率达到该比例时告警 / 触发压缩（D3 复用同一常量）。
# 为什么是 0.75 不是 1.0：1.0 = 窗口已经满了，那时连"这轮要发的消息 +
# 模型要输出的答案"都塞不下；75% 触发，留给输入输出 25% 的余量。
COMPRESS_THRESHOLD = 0.75


class ContextReport(BaseModel):
    """一次 check 的结果：用量、预算、使用率、是否触发压缩。

    相当于体检报告单：check() 负责量，Report 负责把量装进一个结构体带回。
    """

    total_tokens: int = 0  # 当前 messages 一共多少 token
    budget: int = 0  # 预算上限（窗口 × 0.75）
    # float = 浮点数（带小数）。ge=0.0 是 Field 的约束参数：
    # ge = greater or equal（大于等于）——usage_ratio 不允许小于 0，
    # 传负数会在构造时报错。pydantic 会在赋值时自动检查这个约束。
    usage_ratio: float = Field(default=0.0, ge=0.0)  # 使用率 = total / budget（0~1）
    should_compress: bool = False  # True 表示该压缩了（usage >= 75%）


class ContextWindow:
    """上下文预算窗口。两种构造：直接给 budget，或由模型窗口 × 安全系数推导。

    __init__ 是 Python 的"构造方法"：Message(...) 或 ContextWindow(...)
    创建实例时自动调用它，用来初始化实例属性（这里的 self.budget）。
    """

    def __init__(self, budget: int) -> None:
        # 防呆校验：预算必须是正数。为什么在这拦：budget <= 0 时后面的
        # usage = total / budget 会除零崩溃（ZeroDivisionError），或算出
        # 负使用率的荒唐结果。与其让错误在几层之后以诡异方式爆出来，
        # 不如在入口处就 raise 一个清晰的 ValueError，一眼看懂哪错了。
        if budget <= 0:
            raise ValueError(f"budget 必须为正整数，收到 {budget}")
        self.budget = budget  # 记住预算（实例属性，之后 check() 要用）

    # @classmethod = 类方法：与 @staticmethod 类似"不依赖某个具体实例"，
    # 但区别是它接收 cls（类本身），可以用 cls(...) 来【创建该类的实例】。
    # 用途：提供"另一种构造方式"——本来的构造是 ContextWindow(budget)，
    # from_model 则让你用"模型窗口 × 安全系数"来造，内部替你算好预算：
    #     ContextWindow.from_model(8192)   # → budget = 6144
    # 调用时用类名：ContextWindow.from_model(...)，不需要先有实例。
    # 返回注解写 "ContextWindow"（带引号字符串）：类方法定义时类还在构造
    # 中，不能直接引用自己的名字，加引号延迟解析（见 messages.py 同款注释）。
    @classmethod
    def from_model(cls, window_tokens: int, safety_ratio: float = 0.75) -> "ContextWindow":
        """budget = 模型窗口 × 安全系数（主文档契约）。"""
        return cls(int(window_tokens * safety_ratio))
        # int(...) 把乘法结果转成整数（8192*0.75=6144.0 → 6144）。
        # 用 cls 而不是 ContextWindow：万一以后有人继承 ContextWindow，
        # from_model 也会正确造出【子类】实例（而不是写死父类）。

    def check(self, messages: list[Message], counter: TokenCounter) -> ContextReport:
        """统计 messages 总量并返回使用率报告；should_compress 由 75% 阈值决定。

        调用方（chat.py）每轮对话后调一次，就像看一眼内存表。
        """
        total = counter.count_messages(messages)  # 先数总数（counter.py 的活）
        usage = total / self.budget
        # 注意：Python 3 里 / 是"真除法"，5 / 2 = 2.5（带小数，float）。
        # 如果写 // 才是整除（5 // 2 = 2）。这里需要精确比例所以用 /。
        return ContextReport(
            total_tokens=total,
            budget=self.budget,
            usage_ratio=usage,
            should_compress=usage >= COMPRESS_THRESHOLD,  # 比较运算的结果直接是 bool
        )