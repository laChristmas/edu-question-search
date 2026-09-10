"""OCR、附图裁剪与墨迹匹配。"""

from eqsearch.vision.diagram import (
    canonicalize_figure,
    diagram_similarity,
    histogram_vector,
    ink_vector,
    mean_diagram_vector,
)
from eqsearch.vision.mathocr import merge_line_with_latex, looks_like_formula
from eqsearch.vision.ocr import (
    OcrBackend,
    OcrResult,
    PassthroughOcr,
    PaddleOcrBackend,
    RapidOcrBackend,
    get_ocr_backend,
    open_image,
)
from eqsearch.vision.phash import hamming_distance, perceptual_hash

__all__ = [
    "looks_like_formula",
    "merge_line_with_latex",
    "OcrBackend",
    "OcrResult",
    "PassthroughOcr",
    "PaddleOcrBackend",
    "RapidOcrBackend",
    "get_ocr_backend",
    "open_image",
    "histogram_vector",
    "ink_vector",
    "mean_diagram_vector",
    "canonicalize_figure",
    "diagram_similarity",
    "hamming_distance",
    "perceptual_hash",
]
