import json
import os

from afg.exceptions import AfgError
from afg.observability.logging import get_logger

MARKDOWN_SUFFIX = ".md"
SECTION_MARK = "## "
# BGE 检索的用法：文档侧不加前缀，query 侧加这一句，让"问题"和"答案"在向量空间里靠得更近
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def default_title(source):
    if source.endswith(MARKDOWN_SUFFIX):
        return source[: -len(MARKDOWN_SUFFIX)]
    return source


def chunk_text(chunk):
    return chunk["title"] + "\n" + chunk["text"]


def make_chunk(source, title, text):
    return {"source": source, "title": title, "text": text.strip()}


def split_chunks(source, text, max_chars):
    chunks = []
    title = ""
    body = ""
    for line in text.splitlines():
        if line.startswith(SECTION_MARK):
            if title:
                add_section(chunks, source, title, body, max_chars)
            title = line[len(SECTION_MARK) :].strip()
            body = ""
        else:
            body = body + line + "\n"
    if title:
        add_section(chunks, source, title, body, max_chars)
    # 标题之前那段是"固定格式说明"之类的元信息，不是正文，有标题的文件就跳过它；
    # 整篇没有任何 ## 的文件（比如一篇散文）才退化成整篇一个块
    if not chunks:
        chunks.append(make_chunk(source, default_title(source), text))
    return chunks


def add_section(chunks, source, title, body, max_chars):
    buffer = ""
    for paragraph in body.split("\n\n"):
        text = paragraph.strip()
        if not text:
            continue
        if buffer and len(buffer) + len(text) > max_chars:
            chunks.append(make_chunk(source, title, buffer))
            buffer = ""
        # 一个段落自己就超过 max_chars 时不再从中间切断，宁可这块大一点也别把句子劈两半
        buffer = buffer + text + "\n\n"
    if buffer:
        chunks.append(make_chunk(source, title, buffer))


def cache_signature(config):
    # 换了分块大小或换了 embedding 模型，旧向量就作废了 —— 签名对不上整份缓存直接丢掉
    return {"max_chars": config.max_chunk_chars, "embedder": config.embedder_dir}


def load_cache(index_path, signature):
    if not os.path.isfile(index_path):
        return {}
    try:
        data = json.loads(read_text(index_path))
    except ValueError:
        return {}
    if data.get("signature") != signature:
        return {}
    if "files" not in data:
        return {}
    return data["files"]


def save_cache(index_path, signature, files):
    with open(index_path, "w", encoding="utf-8") as handle:
        json.dump({"signature": signature, "files": files}, handle, ensure_ascii=False)


def build_index(config, embedder):
    if not os.path.isdir(config.corpus_dir):
        raise AfgError(
            "语料目录不存在：" + config.corpus_dir,
            context={"hint": "把要检索的 markdown 放进这个目录，或改 SearchConfig.corpus_dir"},
        )
    signature = cache_signature(config)
    cached = load_cache(config.index_path, signature)
    files = {}
    embedded = 0
    for name in sorted(os.listdir(config.corpus_dir)):
        if not name.endswith(MARKDOWN_SUFFIX):
            continue
        path = os.path.join(config.corpus_dir, name)
        mtime = os.path.getmtime(path)
        entry = cached.get(name)
        if entry is not None and entry["mtime"] == mtime:
            files[name] = entry
            continue
        # 这篇笔记改了（或者第一次见）才重新分块、重算向量；没改的连模型都不用跑
        chunks = split_chunks(name, read_text(path), config.max_chunk_chars)
        texts = []
        for chunk in chunks:
            texts.append(chunk_text(chunk))
        vectors = embedder.embed(texts)
        for index in range(len(chunks)):
            chunks[index]["vector"] = vectors[index]
        files[name] = {"mtime": mtime, "chunks": chunks}
        embedded = embedded + len(chunks)
    if embedded:
        save_cache(config.index_path, signature, files)
    chunks = []
    for name in files:
        for chunk in files[name]["chunks"]:
            chunks.append(chunk)
    logger = get_logger("rag")
    logger.info("rag.index", files=len(files), chunks=len(chunks), embedded=embedded)
    return chunks


def dot(left, right):
    total = 0.0
    for index in range(len(left)):
        total = total + left[index] * right[index]
    return total


def cosine_top_k(chunks, query_vector, k):
    ranked = []
    for position in range(len(chunks)):
        score = dot(query_vector, chunks[position]["vector"])
        ranked.append((score, position))
    ranked.sort(reverse=True)
    hits = []
    used = {}
    for index in range(len(ranked)):
        if len(hits) >= k:
            break
        pair = ranked[index]
        chunk = chunks[pair[1]]
        # 一个小节被切成好几块时只留最相关的第一块，否则 Top-3 会被同一个小节占满
        key = chunk["source"] + "|" + chunk["title"]
        if key in used:
            continue
        used[key] = True
        hits.append(
            {
                "score": round(pair[0], 4),
                "source": chunk["source"],
                "title": chunk["title"],
                "text": chunk["text"],
            }
        )
    return hits


def search(config, query, k=None, embedder=None):
    if k is None:
        k = config.top_k
    if embedder is None:
        # 到这一步才导入 embedder：单测注入假 embedder 时不碰 torch，省掉两秒多的启动
        from afg.rag.embedder import get_embedder

        embedder = get_embedder(config.embedder_dir)
    chunks = build_index(config, embedder)
    if not chunks:
        return []
    query_vector = embedder.embed([QUERY_PREFIX + query])[0]
    hits = cosine_top_k(chunks, query_vector, k)
    top = ""
    if hits:
        top = hits[0]["source"]
    logger = get_logger("rag")
    logger.info("rag.search", query=query, k=k, hits=len(hits), top_source=top)
    return hits
