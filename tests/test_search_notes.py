import pytest

from afg.config import SearchConfig
from afg.exceptions import ToolError
from afg.rag.index import search, split_chunks
from afg.tools.search_notes import search_notes

HEADINGS_NOTE = """# 文件标题

> 这段是固定格式说明，不是正文

## Q1：甲是什么

甲的内容。

## Q2：乙是什么

乙的内容。
"""

KEYWORDS_NOTE = """## Q1：甲

甲的内容在这里。

## Q2：乙

乙的内容在这里。

## Q3：丙

丙的内容在这里。
"""


class FakeEmbedder:
    """按关键词给固定向量，让排序能脱网、可预测地测出来，不用加载真模型。"""

    def __init__(self):
        self.seen = []

    def embed(self, texts):
        vectors = []
        for text in texts:
            self.seen.append(text)
            vectors.append(self._vector_for(text))
        return vectors

    def _vector_for(self, text):
        if "甲" in text:
            return [1.0, 0.0]
        if "乙" in text:
            return [0.0, 1.0]
        return [-1.0, 0.0]


def make_config(tmp_path, max_chars=200):
    return SearchConfig(
        corpus_dir=str(tmp_path),
        index_path=str(tmp_path / "index.json"),
        embedder_dir="fake-model",
        max_chunk_chars=max_chars,
    )


def write_note(directory, name, text):
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def titles_of(hits):
    titles = []
    for hit in hits:
        titles.append(hit["title"])
    return titles


def test_split_chunks_skips_preamble_and_uses_section_titles():
    chunks = split_chunks("a.md", HEADINGS_NOTE, 200)

    assert len(chunks) == 2
    assert chunks[0]["title"] == "Q1：甲是什么"
    assert chunks[0]["text"] == "甲的内容。"
    assert chunks[1]["title"] == "Q2：乙是什么"


def test_file_without_headings_becomes_one_chunk():
    chunks = split_chunks("essay.md", "一整篇没有小标题的正文。", 200)

    assert len(chunks) == 1
    assert chunks[0]["title"] == "essay"
    assert chunks[0]["text"] == "一整篇没有小标题的正文。"


def test_long_section_splits_by_paragraph():
    paragraph = "甲" * 120
    text = "## Q1：甲\n\n" + paragraph + "\n\n" + paragraph + "\n\n" + paragraph + "\n"

    chunks = split_chunks("a.md", text, 200)

    assert len(chunks) == 3
    assert chunks[0]["title"] == "Q1：甲"
    assert chunks[2]["title"] == "Q1：甲"


def test_top_k_orders_by_similarity(tmp_path):
    write_note(tmp_path, "a.md", KEYWORDS_NOTE)

    hits = search(make_config(tmp_path), "甲", k=3, embedder=FakeEmbedder())

    assert titles_of(hits) == ["Q1：甲", "Q2：乙", "Q3：丙"]


def test_top_k_keeps_only_one_chunk_per_section(tmp_path):
    paragraph = "甲" * 120
    text = "## Q1：甲\n\n" + paragraph + "\n\n" + paragraph + "\n\n## Q2：乙\n\n乙的内容。\n"
    write_note(tmp_path, "a.md", text)

    hits = search(make_config(tmp_path), "甲", k=3, embedder=FakeEmbedder())

    assert titles_of(hits) == ["Q1：甲", "Q2：乙"]


def test_cache_reuses_vectors_for_unchanged_files(tmp_path):
    write_note(tmp_path, "a.md", KEYWORDS_NOTE)
    config = make_config(tmp_path)
    fake = FakeEmbedder()

    search(config, "甲", embedder=fake)
    first = len(fake.seen)

    fake.seen.clear()
    search(config, "甲", embedder=fake)

    assert first == 4
    assert len(fake.seen) == 1


def test_cache_is_discarded_when_chunk_size_changes(tmp_path):
    write_note(tmp_path, "a.md", KEYWORDS_NOTE)
    fake = FakeEmbedder()

    search(make_config(tmp_path, max_chars=200), "甲", embedder=fake)
    fake.seen.clear()

    search(make_config(tmp_path, max_chars=50), "甲", embedder=fake)

    assert len(fake.seen) > 1


def test_tool_schema_marks_query_required():
    schema = search_notes.parameters()

    assert schema["required"] == ["query"]
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["k"]["type"] == "integer"


def test_tool_rejects_empty_query():
    with pytest.raises(ToolError):
        search_notes.run(query="   ")
