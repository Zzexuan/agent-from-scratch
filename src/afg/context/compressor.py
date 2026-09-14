from afg.context.messages import Message

SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话历史压缩器。把下面这段对话压缩成一段简短摘要，遵守三条规则：\n"
    "1. 保留：任务目标、关键决策、重要发现、还没解决的问题、犯过的错误。\n"
    "2. 丢弃：过程性描述、寒暄、重复内容、完整的原始输出。\n"
    "3. 直接输出摘要正文，不要加任何开头语或解释。"
)

SUMMARY_PREFIX = "[历史摘要] "

PRIMER_COUNT = 3


class Compressor:
    def __init__(self, budget, target_ratio=0.375, min_keep_recent=4):
        if budget <= 0:
            raise ValueError(f"budget 必须为正整数，收到 {budget}")
        self.budget = budget
        self.target_ratio = target_ratio
        self.min_keep_recent = min_keep_recent

    def compress(self, messages, llm, counter, keep_recent=20):
        primers = messages[:PRIMER_COUNT]

        available = len(messages) - PRIMER_COUNT
        if available <= 0:
            return messages

        # 至少给中间段留 1 条：否则 keep_recent 会把所有消息都当成"最近"，
        # 中间段为空 → 压缩空转（预算调小、或消息条数少时会踩到）。
        # 同时这行保证【最后一条】永远保留 —— 那是用户当前这轮，不能被压进摘要。
        recent_count = min(keep_recent, available - 1)
        if recent_count < 1:
            return messages

        while True:
            middle = messages[PRIMER_COUNT : len(messages) - recent_count]
            if len(middle) == 0:
                return messages

            summary_text = self._summarize(middle, llm)
            # 摘要用 system 角色插在对话中间：这是 D3 规格的要求。
            # 协议上 system 惯例放最前，放中间能用但不标准；换供应商时留意。
            summary_message = Message(role="system", content=SUMMARY_PREFIX + summary_text)

            recent = messages[len(messages) - recent_count :]
            result = primers + [summary_message] + recent

            if counter.count_messages(result) <= self.budget * self.target_ratio:
                return result
            if recent_count <= self.min_keep_recent:
                return result
            # 一次没压到位就减半再压：摘要要重生成，因为丢掉的 Recents 会并进中间段，
            # 不重生成就会永久丢失（压缩可以有损，但不能悄悄丢）。
            recent_count = recent_count // 2

    def _summarize(self, middle, llm):
        text = ""
        for m in middle:
            if m.content:
                text += m.role + "：" + m.content + "\n"
            if m.tool_calls:
                for tc in m.tool_calls:
                    text += "assistant：调用工具 " + tc.name + "\n"

        prompt = [
            Message(role="system", content=SUMMARY_SYSTEM_PROMPT),
            Message(role="user", content=text),
        ]
        resp = llm.chat(prompt, temperature=0.3)
        if resp.content:
            return resp.content
        return "（摘要生成失败）"
