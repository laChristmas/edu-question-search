"""题库条目、查询记录与打分结果。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GalleryItem(BaseModel):
    """一条入库题目。original_text 是展示用题干；normalized/structure 用于匹配。"""

    model_config = ConfigDict(extra="ignore")

    id: str
    original_text: str
    """人类可读题干（Geometry3K 优先 problem_text）。"""
    normalized_text: str
    """去空白、去 LaTeX 后的表面文本；几何题可能含索引用 logic form。"""
    structure_text: str
    """数量替换为 NUM 后的结构文本，用于召回与变式。"""
    equation: str | None = None
    equation_template: str | None = None
    phash: str | None = None
    """附图感知哈希，只来自裁出的配图。"""
    diagram_vector: list[float] | None = None
    """附图 16×16 墨迹向量。"""
    original_cluster_id: str | None = None
    variant_group_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class QueryRecord(BaseModel):
    """一次查询：题干来自用户输入或 OCR，附图只来自裁剪后的配图。"""

    text: str = ""
    normalized_text: str = ""
    structure_text: str = ""
    equation: str | None = None
    equation_template: str | None = None
    phash: str | None = None
    diagram_vector: list[float] | None = None
    has_diagram: bool = False
    ocr_ok: bool = True
    use_formula: bool = True
    """True：题干∧公式∧附图。False：只比题干∧附图，不抽公式。"""
    from_image: bool = False


class ScoredCandidate(BaseModel):
    """召回后的候选。relation: original / variant / related / unrelated。"""

    item: GalleryItem
    retrieval_score: float
    surface: float
    structure: float
    phash_distance: int | None = None
    formula_score: float = 0.0
    diagram_score: float | None = None
    is_original: bool = False
    is_variant: bool = False
    final_score: float = 0.0
    relation: str = "related"


class SearchResponse(BaseModel):
    query_text: str
    results: list[ScoredCandidate]
    originals: int = 0
    recalled: int = 0
    reranked: int = 0
    has_diagram: bool = False
    math_ocr: bool = True
    formula_engine: bool | None = None
