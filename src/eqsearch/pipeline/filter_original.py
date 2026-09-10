"""原题判定。公式检测开：题干∧公式∧附图；关：题干∧附图。"""

from __future__ import annotations

from eqsearch.config import SearchConfig
from eqsearch.models import QueryRecord, ScoredCandidate
from eqsearch.text.formula import formula_template_blob, formulas_compatible
from eqsearch.text.normalize import normalize_text, quantities_equal, quantity_tokens
from eqsearch.text.similarity import surface_similarity
from eqsearch.vision.diagram import diagram_similarity
from eqsearch.vision.phash import hamming_distance


def stem_matches(query: QueryRecord, candidate: ScoredCandidate, config: SearchConfig) -> bool:
    """题干是否同一道题。公式检测开时先把式子遮住，只比叙述。"""
    from eqsearch.text.formula import mask_formula_text, source_question_text

    item_src = source_question_text(candidate.item.original_text)
    query_src = source_question_text(query.text)
    if query.use_formula:
        qn = normalize_text(mask_formula_text(query_src))
        item_stem = normalize_text(mask_formula_text(item_src))
    else:
        qn = normalize_text(query_src)
        item_stem = normalize_text(item_src)
    item_full = candidate.item.normalized_text
    thresh = config.t_ocr_same if query.from_image else config.t_same
    if qn and qn in {item_full, item_stem}:
        return True
    stem_surface = surface_similarity(qn, item_stem)
    if quantities_equal(qn, item_stem) and stem_surface >= thresh:
        return True
    # OCR may append figure labels; Geometry3K stems often have leftover LaTeX.
    if quantity_tokens(qn) and quantities_equal(qn, item_stem) and qn and item_stem:
        shorter, longer = (qn, item_stem) if len(qn) <= len(item_stem) else (item_stem, qn)
        if len(shorter) >= 24 and shorter in longer:
            return True
    same_numbers = quantities_equal(qn, item_full)
    return same_numbers and (stem_surface if query.use_formula else candidate.surface) >= thresh


def formula_matches(query: QueryRecord, candidate: ScoredCandidate, config: SearchConfig) -> bool:
    from eqsearch.text.formula import formula_atom_templates, source_question_text
    from eqsearch.text.similarity import structure_similarity

    item_blob = formula_template_blob(candidate.item.original_text)
    text_blob = formula_template_blob(query.text)
    query_blob = query.equation_template or text_blob
    if (
        query.equation_template
        and text_blob
        and query.equation_template != text_blob
        and text_blob.replace(" ", "") in query.equation_template.replace(" ", "")
    ):
        query_blob = text_blob
    candidate.formula_score = 1.0 if (query_blob and item_blob and query_blob == item_blob) else 0.0
    if query_blob and item_blob:
        candidate.formula_score = structure_similarity(query_blob, item_blob)
    if formulas_compatible(query_blob, item_blob, config.t_formula):
        return True
    if (
        query.equation_template
        and text_blob
        and query.equation_template != text_blob
        and text_blob.replace(" ", "") not in query.equation_template.replace(" ", "")
    ):
        return False
    q_atoms = formula_atom_templates(source_question_text(query.text))
    i_atoms = formula_atom_templates(candidate.item.original_text)
    if q_atoms and q_atoms == i_atoms:
        candidate.formula_score = max(candidate.formula_score, 1.0)
        return True
    return False


def diagram_matches(query: QueryRecord, candidate: ScoredCandidate, config: SearchConfig) -> bool:
    """Compare attached figures only. Full-photo hashes must not reach here."""
    sim = diagram_similarity(query.diagram_vector, candidate.item.diagram_vector)
    distance = hamming_distance(query.phash, candidate.item.phash)
    candidate.phash_distance = distance
    candidate.diagram_score = sim
    query_has = bool(query.diagram_vector or query.phash)
    item_has = bool(candidate.item.diagram_vector or candidate.item.phash)
    if not query_has or not item_has:
        return True
    if sim is not None and sim >= config.t_diagram:
        return True
    if distance is not None and distance <= config.phash_hamming_max:
        return True
    return False


def is_original(
    query: QueryRecord,
    candidate: ScoredCandidate,
    config: SearchConfig,
) -> bool:
    """原题：题干∧附图；开启公式检测时再 ∧ 公式兼容。"""
    if not stem_matches(query, candidate, config):
        return False
    if query.use_formula and not formula_matches(query, candidate, config):
        return False
    if not diagram_matches(query, candidate, config):
        return False
    return True


def mark_originals(
    query: QueryRecord,
    candidates: list[ScoredCandidate],
    config: SearchConfig,
) -> tuple[list[ScoredCandidate], int]:
    count = 0
    for cand in candidates:
        if query.use_formula:
            formula_matches(query, cand, config)
        else:
            cand.formula_score = 0.0
        diagram_matches(query, cand, config)
        if is_original(query, cand, config):
            cand.is_original = True
            cand.relation = "original"
            count += 1
    return candidates, count
