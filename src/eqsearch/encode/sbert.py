from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np

from eqsearch.encode.base import l2_normalize


class SentenceTransformerEncoder:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5") -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("未安装 sentence-transformers。") from exc
        self.model_name = model_name
        self.model = SentenceTransformer(model_name)

    def fit(self, texts: Sequence[str]) -> None:
        return None

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = self.model.encode(
            list(texts),
            normalize_embeddings=False,
            show_progress_bar=False,
        )
        return l2_normalize(np.asarray(vectors, dtype=np.float32))

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "sbert_name.txt").write_text(self.model_name, encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> SentenceTransformerEncoder:
        name = (path / "sbert_name.txt").read_text(encoding="utf-8").strip()
        return cls(model_name=name)
