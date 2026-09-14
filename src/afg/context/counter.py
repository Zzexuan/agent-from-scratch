"""token 计数：真实 tokenizer 优先，不可用时按字数估算（D2 主文档规格）。

新手阅读顺序：
1. 先读 count() 方法（核心：一段文本几个 token）。
2. 再读 __init__ / _load_encoding()（tokenizer 从哪来、失败怎么办）。
3. 最后读 count_messages()（多条消息合计，D4 起工具消息也算）。

八股要点（D02 笔记）：
- 成本估算必须用真实 tokenizer 不能拍脑袋；本模块用 tiktoken `cl100k_base`。
- DeepSeek 未公开自家 tokenizer，cl100k 只是近似——工程上接受近似 + 安全余量
  （预算 = 窗口 × 0.75 就是余量），面试官爱追问这个取舍。
"""

import json
from typing import Any

from afg.context.messages import Message

# 估算系数：无 tokenizer 可用时 1 个汉字 ≈ 1 token 的粗估
# （cl100k 下中文约 1 字 ≈ 1.5-2 token，0.6 系数是保守下限，宁低估不虚高）
_FALLBACK_TOKENS_PER_CHAR = 0.6


class TokenCounter:
    """统计文本 / 消息列表的 token 数。

    `prefer_tiktoken=False` 强制走估算分支，供回退路径单测使用。

    设计思想：tiktoken 是"真家伙"（准），但要联网下载词表、可能没装包；
    估算永远是"备胎"（不准但不崩）。双轨制 = 优先精确、失败自动降级，
    绝不让"数 token"这种辅助功能成为程序的硬依赖。
    """

    def __init__(self, prefer_tiktoken: bool = True) -> None:
        # self._encoding 的类型注解是 Any | None：
        #   Any    = "任何类型都行"（tiktoken 的编码对象没有现成类型可标，
        #            所以用 Any 表示"我知道它是个编码器，但懒得精确描述"）
        #   | None = 加载失败时会是 None，见 _load_encoding()
        # 这行调 _load_encoding()：成功 → 存编码器；失败 → 存 None，
        # 之后 count() 看到 None 就知道要走估算分支。
        self._encoding: Any | None = self._load_encoding() if prefer_tiktoken else None

    @staticmethod
    def _load_encoding() -> Any | None:
        """尝试加载 tiktoken 编码器；任何失败都返回 None（不抛异常）。

        @staticmethod 装饰器 = 静态方法：一个"不需要 self（实例）"的方法。
        普通方法第一个参数是 self（拿到实例），静态方法没有——因为它
        不读实例的任何数据，只做"加载编码器"这一件事，逻辑上属于类
        而不是某个具体实例。调用方式：TokenCounter._load_encoding()。
        """
        try:
            import tiktoken  # OpenAI 的 tokenizer 库（第三方，见 pyproject）
        except ImportError:
            # 包未安装：静默降级到估算，不让计数成为硬依赖
            return None
        try:
            return tiktoken.get_encoding("cl100k_base")
        except (KeyError, OSError):
            # 编码名不存在 / 首次加载下载 BPE 文件但网络不可用
            return None

    def count(self, text: str) -> int:
        """单段文本的 token 数；空文本返回 0。"""
        if not text:  # 空字符串 / None → 0 个 token（省得下面白算）
            return 0
        if self._encoding is not None:  # 有真编码器 → 用真家伙
            return len(self._encoding.encode(text))  # encode = 文本切成 token 列表
        # 估算分支：len(text) 是字符数（中文 1 字 = 1 个字符），乘 0.6 系数。
        # max(1, ...) 防止"1 个字符 × 0.6 → int 得 0"——至少算 1 个 token，
        # 否则短文本会被数成 0，预算统计失真。
        return max(1, int(len(text) * _FALLBACK_TOKENS_PER_CHAR))

    def count_messages(self, messages: list[Message]) -> int:
        """整条消息列表的 token 数：content + tool_calls 参数 + tool_call_id 全算。

        把 role=tool 的调用参数也算进预算，是为 D4 起工具型 Agent 预留的精确口径。
        （一条消息发出去时 content/工具名/参数/call_id 全都会占 token，
        只数 content 会严重低估真实消耗。）
        """
        total = 0
        for msg in messages:  # 遍历每一条消息，把它的各个部分都加起来
            if msg.content:  # 有文本 → 数文本（None/空串不数）
                total += self.count(msg.content)
            if msg.tool_calls:  # 带工具调用 → 数工具名 + 参数
                for tc in msg.tool_calls:
                    total += self.count(tc.name)
                    # json.dumps(dict) = 把 Python 字典转回 JSON 字符串再数。
                    # 为什么：发给 API 时参数就是以 JSON 文本形式传输的，
                    # 所以要按"文本"的口径数 token。
                    # ensure_ascii=False：中文参数不转成 \uXXXX 转义，
                    # 保持可读（转义后 token 数也会变，口径就不一致了）。
                    total += self.count(json.dumps(tc.arguments, ensure_ascii=False))
            if msg.tool_call_id:  # tool 消息的"回答哪张派工单"的 id 也占 token
                total += self.count(msg.tool_call_id)
        return total