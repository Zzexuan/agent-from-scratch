"""token 计数：真实 tokenizer 优先，不可用时按字数估算（D2 主文档规格）。

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
    """

    def __init__(self, prefer_tiktoken: bool = True) -> None:
        self._encoding: Any | None = self._load_encoding() if prefer_tiktoken else None

    @staticmethod
    def _load_encoding() -> Any | None:
        try:
            import tiktoken
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
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, int(len(text) * _FALLBACK_TOKENS_PER_CHAR))

    def count_messages(self, messages: list[Message]) -> int:
        """整条消息列表的 token 数：content + tool_calls 参数 + tool_call_id 全算。

        把 role=tool 的调用参数也算进预算，是为 D4 起工具型 Agent 预留的精确口径。
        """
        total = 0
        for msg in messages:
            if msg.content:
                total += self.count(msg.content)
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    total += self.count(tc.name)
                    total += self.count(json.dumps(tc.arguments, ensure_ascii=False))
            if msg.tool_call_id:
                total += self.count(msg.tool_call_id)
        return total