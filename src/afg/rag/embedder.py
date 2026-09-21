import os

import torch
from transformers import AutoModel, AutoTokenizer

from afg.exceptions import AfgError

BATCH_SIZE = 16

_EMBEDDERS = {}


class LocalEmbedder:
    def __init__(self, model_dir):
        # 模型目录不存在时给一句人话提示，别让 transformers 抛出几十行堆栈
        if not os.path.isdir(model_dir):
            raise AfgError(
                "本地 embedding 模型不存在：" + model_dir,
                context={"hint": "先下载：python -m afg.rag.download"},
            )
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self._model = AutoModel.from_pretrained(model_dir)
        self._model.eval()

    def embed(self, texts):
        vectors = []
        for start in range(0, len(texts), BATCH_SIZE):
            group = texts[start : start + BATCH_SIZE]
            vectors.extend(self._embed_group(group))
        return vectors

    def _embed_group(self, texts):
        inputs = self._tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
        with torch.no_grad():
            outputs = self._model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )
        hidden = outputs.last_hidden_state
        # hidden 是 (条数, token 数, 512) 三维张量，: 表示"这维全要"，0 表示取第 0 个 token
        # （BGE 约定用开头的 CLS 位代表整句话，不是把每个 token 平均）
        cls_vector = hidden[:, 0]
        vectors = torch.nn.functional.normalize(cls_vector, p=2, dim=1)
        return vectors.tolist()


def get_embedder(model_dir):
    if model_dir not in _EMBEDDERS:
        _EMBEDDERS[model_dir] = LocalEmbedder(model_dir)
    return _EMBEDDERS[model_dir]
