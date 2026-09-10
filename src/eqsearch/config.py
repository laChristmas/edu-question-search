"""检索阈值。改阈值不必重新入库；改附图向量或编码器需要重新 ingest。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchConfig:
    recall_k: int = 80
    """向量召回条数。"""
    rerank_k: int = 32
    """进入精排的变式上限（不含已占用名额的原题）。"""
    max_results: int = 3
    """最终返回条数上限。"""
    t_same: float = 0.90
    """原题题干表面相似度阈值。"""
    t_ocr_same: float = 0.82
    """拍照 OCR 题干略松，避免识别噪声掉原题。"""
    t_var: float = 0.85
    """变式结构相似度阈值。"""
    surface_gap: float = 0.08
    phash_hamming_max: int = 10
    """附图感知哈希最大汉明距离，作为墨迹相似度的补充。"""
    min_final_score: float = 0.38
    """精排后截断分数。"""
    unrelated_structure_max: float = 0.45
    """低于此结构分视为无关，不标成变式。"""
    drop_unrelated_before_rerank: bool = True
    visual_blend: float = 0.35
    """召回时附图向量相对文本向量的拼接权重。"""
    t_formula: float = 0.82
    t_diagram: float = 0.62
    """附图墨迹余弦相似度阈值。"""
    generic_stem_chars: int = 24
    """短于此时，不同附图不得标成变式（避免“求阴影面积”一类空泛题干误召回）。"""
