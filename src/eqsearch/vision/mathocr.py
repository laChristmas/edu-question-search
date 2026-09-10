"""公式检测辅助：开关、题干与 LaTeX 合并。读图模型见 vision.read_question。"""

from __future__ import annotations

import os
import re
from typing import Callable

from PIL import Image

from eqsearch.vision.layout import OcrLine

_MATH_HINT = re.compile(
    r"[=≤≥≠≈∫∑√∞πθαβγΔλμσφψω∂∇\\^_]|\\frac|\\sqrt|\\sum|\\int|"
    r"\b(sin|cos|tan|log|ln|sqrt|frac|lim)\b|"
    r"[A-Za-z]\s*\([^)]{0,24}\)\s*=|"
    r"\^[\{\(]?-?1"
)
_LATEX_KEEP = re.compile(r"[A-Za-z\\{}_\^+\-=/\d]")
_PROSE_WORDS = {
    "the",
    "and",
    "for",
    "of",
    "what",
    "is",
    "are",
    "find",
    "then",
    "when",
    "with",
    "that",
    "this",
    "which",
    "range",
    "function",
    "functions",
    "express",
    "answer",
    "common",
    "fraction",
    "means",
    "graph",
    "drawn",
    "without",
    "lifting",
    "pencil",
    "paper",
    "also",
    "denote",
    "these",
    "compute",
    "define",
    "applied",
    "times",
    "between",
    "enter",
    "odd",
    "even",
    "neither",
    "area",
    "square",
    "circle",
    "radius",
    "inches",
    "piecewise",
    "continuous",
    "inverse",
    "inverses",
    "degrees",
    "positive",
    "integers",
    "satisfy",
    "value",
    "such",
    "own",
}
_MAX_CROPS = 8


def math_ocr_enabled() -> bool:
    return parse_math_ocr_flag(None)


def parse_math_ocr_flag(value: object | None = None, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, str) and not value.strip()):
        env = os.environ.get("EQSEARCH_MATH_OCR")
        if env is None or not str(env).strip():
            return default
        value = env
    return str(value).strip().lower() not in {"0", "false", "off", "no", "n"}


def looks_like_formula(text: str) -> bool:
    compact = "".join(text.split())
    if len(compact) < 3:
        return False
    return bool(_MATH_HINT.search(text) or _MATH_HINT.search(compact))


def should_math_ocr_line(text: str) -> bool:
    """Only send formula-only snippets to LaTeX-OCR; mixed English sentences become garbage."""
    if not looks_like_formula(text):
        return False
    words = [w.lower() for w in re.findall(r"[A-Za-z]{3,}", text)]
    prose = [w for w in words if w in _PROSE_WORDS]
    return len(prose) < 3


def formula_engine_available() -> bool:
    from eqsearch.vision.read_question import vision_reader_available

    return vision_reader_available()


def merge_line_with_latex(ocr_text: str, latex: str) -> str:
    ocr_text = (ocr_text or "").strip()
    latex = _clean_latex(latex)
    if not latex:
        return ocr_text
    if not ocr_text:
        return f"${latex}$"
    folded_ocr = re.sub(r"\s+", "", ocr_text).lower()
    folded_tex = re.sub(r"[\s$]", "", latex).lower()
    if folded_tex and folded_tex in folded_ocr:
        return ocr_text
    wrapped = f"${latex}$"
    from eqsearch.text.formula import extract_formula_spans

    spans = extract_formula_spans(ocr_text)
    if len(spans) == 1:
        start, end, _snippet = spans[0]
        return (ocr_text[:start] + " " + wrapped + " " + ocr_text[end:]).strip()
    return f"{ocr_text} {wrapped}"


def merge_stem_with_latex(lines: list[OcrLine], latex_by_index: dict[int, str]) -> str:
    parts: list[str] = []
    for i, line in enumerate(lines):
        parts.append(merge_line_with_latex(line.text, latex_by_index.get(i, "")))
    extra = latex_by_index.get(-1, "")
    if extra:
        parts.append(f"${extra}$")
    return " ".join(part for part in parts if part).strip()


def formula_crop_boxes(
    image: Image.Image,
    lines: list[OcrLine],
) -> list[tuple[int, int, int, int]]:
    """公式区：整行公式、混排行里的式子跨度、文字框外的扁长展示式。"""
    boxes: list[tuple[int, int, int, int]] = []
    for line in lines:
        boxes.extend(_line_formula_boxes(line, image))
    boxes.extend(_display_formula_boxes(image, lines, boxes))
    w, h = image.size
    if h <= 80 and w >= 2 * h:
        boxes.append((0, 0, w, h))
    return _dedupe_boxes(boxes)[:_MAX_CROPS]


def recognize_math_lines(
    image: Image.Image,
    lines: list[OcrLine],
    engine: Callable[[Image.Image], str] | None = None,
    enabled: bool | None = None,
) -> dict[int, str]:
    if enabled is None:
        enabled = math_ocr_enabled()
    if not enabled:
        return {}
    if engine is None:
        return {}
    found: dict[int, str] = {}
    rgb = image.convert("RGB")
    n = 0
    for i, line in enumerate(lines):
        if n >= _MAX_CROPS:
            break
        for box in _line_formula_boxes(line, rgb):
            if n >= _MAX_CROPS:
                break
            crop = _crop_line(rgb, box, pad=4)
            if crop is None:
                continue
            latex = engine(crop)
            if latex:
                found[i] = f"{found.get(i, '')} {latex}".strip()
                n += 1
    if n < _MAX_CROPS:
        extra: list[str] = []
        for box in _display_formula_boxes(rgb, lines, [ln.box for ln in lines]):
            if n >= _MAX_CROPS:
                break
            crop = _crop_line(rgb, box, pad=4)
            if crop is None:
                continue
            latex = engine(crop)
            if latex:
                extra.append(latex)
                n += 1
        if extra:
            found[-1] = " ".join(extra)
    return found


def _line_formula_boxes(
    line: OcrLine,
    image: Image.Image | None = None,
) -> list[tuple[int, int, int, int]]:
    x0, y0, x1, y1 = line.box
    if x1 <= x0 or y1 <= y0:
        return []
    top, bot = y0, y1
    if image is not None:
        top, bot = 0, image.size[1]
    if should_math_ocr_line(line.text):
        return [(x0, top, x1, bot)]
    if not looks_like_formula(line.text):
        return []
    from eqsearch.text.formula import extract_formula_spans

    spans = extract_formula_spans(line.text)
    if not spans:
        return []
    width = x1 - x0
    n = max(len(line.text), 1)
    boxes: list[tuple[int, int, int, int]] = []
    for start, end, _snippet in spans:
        bx0 = x0 + int(width * start / n)
        bx1 = x0 + int(width * end / n)
        if bx1 - bx0 < 12:
            bx1 = min(x1, bx0 + 12)
        boxes.append((bx0, top, bx1, bot))
    return boxes


def _display_formula_boxes(
    image: Image.Image,
    lines: list[OcrLine],
    existing: list[tuple[int, int, int, int]],
) -> list[tuple[int, int, int, int]]:
    import numpy as np

    rgb = image.convert("RGB")
    w, h = rgb.size
    if w < 32 or h < 32:
        return []
    gray = np.asarray(rgb.convert("L"))
    ink = gray < 180
    hide = np.zeros((h, w), dtype=bool)
    pad = max(4, min(w, h) // 80)
    for box in [line.box for line in lines] + list(existing):
        x0, y0, x1, y1 = box
        hide[max(0, y0 - pad) : min(h, y1 + pad), max(0, x0 - pad) : min(w, x1 + pad)] = True
    fig = ink & ~hide
    try:
        import cv2
    except ImportError:
        return []
    kernel = np.ones((3, 3), np.uint8)
    thick = cv2.dilate((fig.astype(np.uint8) * 255), kernel, iterations=2)
    num, _labels, stats, _ = cv2.connectedComponentsWithStats(thick, connectivity=8)
    out: list[tuple[int, int, int, int]] = []
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if bw < 24 or bh < 8 or area < 40:
            continue
        if bh > int(0.28 * h):
            continue
        if bw / max(int(bh), 1) < 2.0:
            continue
        if bw < int(0.12 * w):
            continue
        out.append((int(x), int(y), int(x + bw), int(y + bh)))
    return out[:3]


def _dedupe_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    kept: list[tuple[int, int, int, int]] = []
    for box in boxes:
        x0, y0, x1, y1 = box
        area = max(1, (x1 - x0) * (y1 - y0))
        skip = False
        for ox0, oy0, ox1, oy1 in kept:
            ix0, iy0 = max(x0, ox0), max(y0, oy0)
            ix1, iy1 = min(x1, ox1), min(y1, oy1)
            inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
            if inter / area > 0.6:
                skip = True
                break
        if not skip:
            kept.append(box)
    return kept


def _crop_line(image: Image.Image, box: tuple[int, int, int, int], pad: int = 10) -> Image.Image | None:
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return None
    w, h = image.size
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    if (x1 - x0) < 12 or (y1 - y0) < 8:
        return None
    return image.crop((x0, y0, x1, y1))


def _clean_latex(raw: str | None) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = text.replace("\n", " ").replace("$$", "$")
    text = text.strip("$ ").strip(" ;,.")
    if len(text) < 2 or not _LATEX_KEEP.search(text):
        return ""
    if len(text) > 400:
        text = text[:400]
    if not _latex_looks_real(text):
        return ""
    return text


def _latex_looks_real(text: str) -> bool:
    if text.count(r"\mathrm") >= 2 and len(re.findall(r"[A-Za-z]{4,}", text)) >= 4:
        return False
    if re.search(r"W/nat|furcthor|deegries|trange|trles", text, re.I):
        return False
    return bool(re.search(r"\\(?:frac|sqrt|sum|int|log|sin|cos|tan|left|right|cdot)|[=^_]", text))
