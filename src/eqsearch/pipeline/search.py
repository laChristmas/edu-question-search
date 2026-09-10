"""检索流水线：识图、召回、标原题/变式、精排截断。"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from eqsearch.config import SearchConfig
from eqsearch.index.gallery import Gallery
from eqsearch.index.vector_index import blend_visual
from eqsearch.models import QueryRecord, ScoredCandidate, SearchResponse
from eqsearch.pipeline.filter_original import mark_originals
from eqsearch.pipeline.rerank import cutoff, rerank
from eqsearch.pipeline.variant import tag_variants
from eqsearch.text.formula import formula_template_blob, repair_ocr_math
from eqsearch.text.normalize import equation_template, normalize_text, structure_text
from eqsearch.text.similarity import structure_similarity, surface_similarity
from eqsearch.vision.diagram import canonicalize_figure, mean_diagram_vector
from eqsearch.vision.layout import extract_diagram_crops
from eqsearch.vision.ocr import OcrBackend
from eqsearch.vision.phash import perceptual_hash


def prepare_query(
    text: str = "",
    image: Image.Image | None = None,
    ocr: OcrBackend | None = None,
    math_ocr: bool | None = None,
) -> QueryRecord:
    """从文本和/或照片构造查询。附图只取裁出的配图，不用整张照片。"""
    from eqsearch.vision.mathocr import parse_math_ocr_flag

    use_formula = parse_math_ocr_flag(math_ocr)
    diagram_vector = None
    diagram_phash = None
    ocr_ok = True
    extra_latex = ""
    crops: list[Image.Image] = []
    text_boxes: list[tuple[int, int, int, int]] = []
    if image is not None:
        rgb = image.convert("RGB")
        if ocr is not None:
            result = ocr.recognize(rgb, math_ocr=use_formula)
            if use_formula:
                extra_latex = result.latex or ""
            if not text.strip():
                text = result.text
                ocr_ok = bool(text.strip())
            crops = list(result.diagram_crops)
            text_boxes = [line.box for line in (result.lines or []) if line.box[2] > line.box[0]]
        if not crops:
            crops = extract_diagram_crops(rgb, text_boxes)
        # Never hash or embed the full photo — background clutter is not the problem figure.
        if crops:
            crops = [max(crops, key=lambda im: im.size[0] * im.size[1])]
            diagram_phash = perceptual_hash(canonicalize_figure(crops[0]))
            diagram_vector = mean_diagram_vector(crops)
    if not text.strip():
        if image is not None:
            raise ValueError("查询为空：没有从图片中识别出题目文字，请改填文本后再试。")
        raise ValueError("请填写题目文本或上传题目图片。")
    if use_formula:
        text = repair_ocr_math(text)
    # 列向量/矩阵是题干排版，不是几何配图；当附图会把无图的 MATH 金标挤出召回。
    if crops and use_formula and re.search(r"\\begin\{(?:p|b|B|v)?matrix\}", text):
        crops = []
        diagram_phash = None
        diagram_vector = None
    formula_blob = None
    if use_formula:
        # VL 的 latex 已是题干抽模板，再传入 equation 会叠算一遍导致公式门失败。
        from_text = formula_template_blob(text)
        extra_templ = equation_template(extra_latex) if extra_latex else None
        if extra_templ and extra_templ not in (from_text or ""):
            formula_blob = " ".join(part for part in (from_text, extra_templ) if part)
        else:
            formula_blob = from_text
    return QueryRecord(
        text=text,
        normalized_text=normalize_text(text),
        structure_text=structure_text(text),
        equation=formula_blob,
        equation_template=formula_blob,
        phash=diagram_phash,
        diagram_vector=diagram_vector,
        has_diagram=bool(crops),
        ocr_ok=ocr_ok,
        use_formula=use_formula,
        from_image=image is not None,
    )


def recall(gallery: Gallery, query: QueryRecord, k: int) -> list[ScoredCandidate]:
    """结构文本向量 + 附图向量召回。"""
    text_vec = gallery.encoder.encode([query.structure_text])
    query_visual = [query.diagram_vector]
    q = blend_visual(text_vec, query_visual, gallery.config.visual_blend)
    gdim = gallery.index.vectors.shape[1]
    if q.shape[1] < gdim:
        q = np.pad(q, ((0, 0), (0, gdim - q.shape[1])))
    elif q.shape[1] > gdim:
        q = q[:, :gdim]
    ids, scores = gallery.index.search(q, k)
    out: list[ScoredCandidate] = []
    for idx, score in zip(ids.tolist(), scores.tolist()):
        item = gallery.items[int(idx)]
        out.append(
            ScoredCandidate(
                item=item,
                retrieval_score=float(score),
                surface=surface_similarity(query.normalized_text, item.normalized_text),
                structure=structure_similarity(query.structure_text, item.structure_text),
            )
        )
    return out


def search_without_formula(
    gallery: Gallery,
    text: str = "",
    image: Image.Image | None = None,
    ocr: OcrBackend | None = None,
    config: SearchConfig | None = None,
) -> SearchResponse:
    """不带公式检测：识题干、裁附图，原题 = 题干 ∧ 附图。"""
    return _search(gallery, text=text, image=image, ocr=ocr, config=config, use_formula=False)


def search_with_formula(
    gallery: Gallery,
    text: str = "",
    image: Image.Image | None = None,
    ocr: OcrBackend | None = None,
    config: SearchConfig | None = None,
) -> SearchResponse:
    """带公式检测：识题干与公式、裁附图，原题 = 题干 ∧ 公式 ∧ 附图。"""
    return _search(gallery, text=text, image=image, ocr=ocr, config=config, use_formula=True)


def search(
    gallery: Gallery,
    text: str = "",
    image: Image.Image | None = None,
    ocr: OcrBackend | None = None,
    config: SearchConfig | None = None,
    math_ocr: bool | None = None,
) -> SearchResponse:
    """按公式检测开关分流：开走 search_with_formula，关走 search_without_formula。"""
    from eqsearch.vision.mathocr import parse_math_ocr_flag

    if parse_math_ocr_flag(math_ocr):
        return search_with_formula(gallery, text=text, image=image, ocr=ocr, config=config)
    return search_without_formula(gallery, text=text, image=image, ocr=ocr, config=config)


def _search(
    gallery: Gallery,
    text: str = "",
    image: Image.Image | None = None,
    ocr: OcrBackend | None = None,
    config: SearchConfig | None = None,
    use_formula: bool = True,
) -> SearchResponse:
    config = config or gallery.config
    query = prepare_query(text=text, image=image, ocr=ocr, math_ocr=use_formula)
    recalled = recall(gallery, query, config.recall_k)
    tagged, original_n = mark_originals(query, recalled, config)
    tagged = tag_variants(tagged, config, query=query)
    ranked = rerank(tagged, config, use_formula=use_formula)
    results = cutoff(ranked, config)
    engine_ok = None
    if use_formula and image is not None:
        from eqsearch.vision.mathocr import formula_engine_available

        engine_ok = formula_engine_available()
    return SearchResponse(
        query_text=query.text,
        results=results,
        originals=original_n,
        recalled=len(recalled),
        reranked=len(ranked),
        has_diagram=query.has_diagram,
        math_ocr=use_formula,
        formula_engine=engine_ok,
    )


def search_image_path(
    gallery: Gallery,
    path: Path,
    ocr: OcrBackend,
    extra_text: str = "",
    config: SearchConfig | None = None,
    math_ocr: bool | None = None,
) -> SearchResponse:
    from eqsearch.vision.ocr import open_image

    image = open_image(path)
    return search(
        gallery,
        text=extra_text,
        image=image,
        ocr=ocr,
        config=config,
        math_ocr=math_ocr,
    )
