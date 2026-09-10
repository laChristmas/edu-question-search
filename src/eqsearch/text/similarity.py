"""题干表面相似度与结构相似度（序列比 + n-gram Jaccard）。"""

from __future__ import annotations

from difflib import SequenceMatcher


def _ngrams(text: str, n: int = 3) -> set[str]:
    if not text:
        return set()
    if len(text) < n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def jaccard(a: str, b: str, n: int = 3) -> float:
    left, right = _ngrams(a, n), _ngrams(b, n)
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def sequence_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def surface_similarity(a: str, b: str) -> float:
    return 0.6 * sequence_ratio(a, b) + 0.4 * jaccard(a, b)


def structure_similarity(a: str, b: str) -> float:
    return 0.5 * sequence_ratio(a, b) + 0.5 * jaccard(a, b)
