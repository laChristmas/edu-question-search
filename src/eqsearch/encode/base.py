from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence

import numpy as np


class Encoder(Protocol):
    """Shared-weight bi-encoder (query tower == gallery tower)."""

    def fit(self, texts: Sequence[str]) -> None: ...

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...

    def save(self, path: Path) -> None: ...


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.clip(norms, 1e-8, None)
    return matrix / norms
