import json

_FALLBACK_TOKENS_PER_CHAR = 0.6


class TokenCounter:
    def __init__(self, prefer_tiktoken=True):
        if prefer_tiktoken:
            self._encoding = self._load_encoding()
        else:
            self._encoding = None

    @staticmethod
    def _load_encoding():
        try:
            import tiktoken
        except ImportError:
            return None
        try:
            return tiktoken.get_encoding("cl100k_base")
        except (KeyError, OSError):
            return None

    def count(self, text):
        if not text:
            return 0
        if self._encoding is not None:
            return len(self._encoding.encode(text))
        return max(1, int(len(text) * _FALLBACK_TOKENS_PER_CHAR))

    def count_messages(self, messages):
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
