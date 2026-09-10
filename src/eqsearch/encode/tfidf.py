from __future__ import annotations

from pathlib import Path
from typing import Sequence

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from eqsearch.encode.base import l2_normalize


class TfidfBiEncoder:
    """Character n-gram TF-IDF bi-encoder. Swap for a trained dual-tower later."""

    def __init__(self) -> None:
        self.vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 4),
            min_df=1,
            max_features=80_000,
        )

    def fit(self, texts: Sequence[str]) -> None:
        self.vectorizer.fit(list(texts))

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(list(texts)).astype(np.float32).toarray()
        return l2_normalize(matrix)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.vectorizer, path / "tfidf.joblib")

    @classmethod
    def load(cls, path: Path) -> TfidfBiEncoder:
        encoder = cls()
        encoder.vectorizer = joblib.load(path / "tfidf.joblib")
        return encoder
