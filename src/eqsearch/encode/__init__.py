"""编码器：默认 TF-IDF，可选 sentence-transformers。"""

from __future__ import annotations

from pathlib import Path

from eqsearch.encode.tfidf import TfidfBiEncoder


def build_encoder(kind: str = "tfidf"):
    if kind == "tfidf":
        return TfidfBiEncoder()
    if kind == "sbert":
        from eqsearch.encode.sbert import SentenceTransformerEncoder

        return SentenceTransformerEncoder()
    raise ValueError(f"未知编码器: {kind}")


def load_encoder(path: Path):
    if (path / "tfidf.joblib").exists():
        return TfidfBiEncoder.load(path)
    if (path / "sbert_name.txt").exists():
        from eqsearch.encode.sbert import SentenceTransformerEncoder

        return SentenceTransformerEncoder.load(path)
    raise FileNotFoundError(f"索引目录没有编码器: {path}")
