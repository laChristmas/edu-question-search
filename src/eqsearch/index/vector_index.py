"""向量索引：可选 Faiss，否则 numpy 点积。召回向量 = 文本 ⊕ 加权附图。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from eqsearch.encode.base import l2_normalize
from eqsearch.models import GalleryItem


class VectorIndex:
    def __init__(self, vectors: np.ndarray) -> None:
        self.vectors = l2_normalize(np.asarray(vectors, dtype=np.float32))
        self._faiss = None
        self._try_faiss()

    def _try_faiss(self) -> None:
        try:
            import faiss
        except ImportError:
            return
        index = faiss.IndexFlatIP(self.vectors.shape[1])
        index.add(self.vectors)
        self._faiss = index

    def search(self, query: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
        q = l2_normalize(np.asarray(query, dtype=np.float32).reshape(1, -1))
        k = min(k, len(self.vectors))
        if self._faiss is not None:
            scores, ids = self._faiss.search(q, k)
            return ids[0], scores[0]
        scores = self.vectors @ q.reshape(-1)
        order = np.argpartition(-scores, kth=k - 1)[:k]
        order = order[np.argsort(-scores[order])]
        return order.astype(np.int64), scores[order]

    def save(self, path: Path) -> None:
        np.save(path / "vectors.npy", self.vectors)

    @classmethod
    def load(cls, path: Path) -> VectorIndex:
        return cls(np.load(path / "vectors.npy"))


def blend_visual(
    text_vectors: np.ndarray,
    diagram_vectors: list[list[float] | None],
    weight: float,
) -> np.ndarray:
    if weight <= 0:
        return text_vectors
    dim = 0
    for vec in diagram_vectors:
        if vec:
            dim = len(vec)
            break
    if dim == 0:
        return text_vectors
    visual = np.zeros((len(diagram_vectors), dim), dtype=np.float32)
    for i, vec in enumerate(diagram_vectors):
        if vec:
            visual[i] = np.asarray(vec, dtype=np.float32)
    visual = l2_normalize(visual)
    # Zero visual rows stay zero after normalize clip; they contribute nothing.
    blended = np.concatenate([text_vectors, weight * visual], axis=1)
    return l2_normalize(blended)


def item_visuals(items: list[GalleryItem]) -> list[list[float] | None]:
    return [item.diagram_vector for item in items]
