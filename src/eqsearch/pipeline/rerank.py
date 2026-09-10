"""精排：原题在前，变式按结构等特征打分，最多返回 3 条。"""

from __future__ import annotations

from eqsearch.config import SearchConfig
from eqsearch.models import ScoredCandidate
from eqsearch.text.similarity import surface_similarity


def feature_score(candidate: ScoredCandidate, use_formula: bool = True) -> float:
    if candidate.is_original:
        return 1.2 + 0.1 * candidate.retrieval_score
    gap = max(0.0, candidate.structure - candidate.surface)
    variant_boost = 0.15 if candidate.is_variant else 0.0
    diagram = candidate.diagram_score if candidate.diagram_score is not None else 0.0
    structure_w = 0.40 if use_formula else 0.50
    diagram_w = 0.15 if use_formula else 0.20
    formula_w = 0.15 if use_formula else 0.0
    return (
        structure_w * candidate.structure
        + 0.20 * candidate.retrieval_score
        + formula_w * candidate.formula_score
        + diagram_w * diagram
        + 0.10 * gap
        + variant_boost
        - 0.15 * candidate.surface
    )


def rerank(
    candidates: list[ScoredCandidate],
    config: SearchConfig,
    use_formula: bool = True,
) -> list[ScoredCandidate]:
    pool = [c for c in candidates if c.is_original or c.is_variant]
    originals = [c for c in pool if c.is_original]
    variants = [c for c in pool if c.is_variant]
    pool = originals + variants[: max(0, config.rerank_k - len(originals))]
    for cand in pool:
        cand.final_score = feature_score(cand, use_formula=use_formula)
    pool.sort(key=lambda c: (not c.is_original, -c.final_score))
    return pool


def cutoff(candidates: list[ScoredCandidate], config: SearchConfig) -> list[ScoredCandidate]:
    selected: list[ScoredCandidate] = []
    for cand in candidates:
        if cand.final_score < config.min_final_score:
            continue
        duplicate = False
        for kept in selected:
            same_kind = cand.is_original == kept.is_original
            if (
                same_kind
                and surface_similarity(cand.item.normalized_text, kept.item.normalized_text)
                >= config.t_same
            ):
                duplicate = True
                break
        if duplicate:
            continue
        selected.append(cand)
        if len(selected) >= config.max_results:
            break
    return selected
