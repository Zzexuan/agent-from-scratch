from afg.config import SearchConfig
from afg.exceptions import ToolError
from afg.rag.index import search
from afg.tools.decorator import tool


def format_hits(hits):
    lines = []
    for hit in hits:
        lines.append("【来源：" + hit["source"] + " · " + hit["title"] + "】")
        lines.append(hit["text"])
        lines.append("")
    return "\n".join(lines).strip()


@tool
def search_notes(query: str, k: int = 3) -> str:
    """在我的学习笔记里做语义检索，返回最相关的段落原文和来源文件名。
    回答时请标出引用的是哪个笔记文件。

    :param query: 要检索的问题或关键词，例如：function calling 的四步流程
    :param k: 返回几条最相关的段落，默认 3 条
    """
    if not query.strip():
        raise ToolError("检索关键词不能为空")
    hits = search(SearchConfig(), query, k)
    if not hits:
        return "没有在笔记里检索到相关内容。"
    return format_hits(hits)
