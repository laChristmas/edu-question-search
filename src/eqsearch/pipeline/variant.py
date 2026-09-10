"""变式标注：结构相同且数量不同；短题干配不同图视为无关。"""

from __future__ import annotations

from eqsearch.config import SearchConfig
from eqsearch.models import QueryRecord, ScoredCandidate
from eqsearch.text.normalize import quantities_equal
from eqsearch.vision.diagram import diagram_similarity


def tag_variant(
    candidate: ScoredCandidate,
    config: SearchConfig,
    query: QueryRecord | None = None,
) -> ScoredCandidate:
    if candidate.is_original:
        return candidate
    numbers_differ = True
    if query is not None:
        numbers_differ = not quantities_equal(query.normalized_text, candidate.item.normalized_text)
        if _generic_stem_different_figure(query, candidate, config):
            candidate.relation = "unrelated"
            return candidate
    if numbers_differ and candidate.structure >= config.t_var:
        candidate.is_variant = True
        candidate.relation = "variant"
        return candidate
    if candidate.structure < config.unrelated_structure_max:
        candidate.relation = "unrelated"
        return candidate
    candidate.relation = "related"
    return candidate


def _generic_stem_different_figure(
    query: QueryRecord,
    candidate: ScoredCandidate,
    config: SearchConfig,
) -> bool:
    if len(query.normalized_text) > config.generic_stem_chars:
        return False
    if not query.diagram_vector or not candidate.item.diagram_vector:
        return False
    sim = diagram_similarity(query.diagram_vector, candidate.item.diagram_vector)
    return sim is not None and sim < config.t_diagram


def tag_variants(
    candidates: list[ScoredCandidate],
    config: SearchConfig,
    query: QueryRecord | None = None,
) -> list[ScoredCandidate]:
    return [tag_variant(c, config, query=query) for c in candidates]
