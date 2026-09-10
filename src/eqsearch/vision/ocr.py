"""OCR backends. RapidOCR 识文字框；公式检测开时用开源视觉模型整图读题。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class OcrResult:
    text: str
    latex: str = ""
    diagram_crops: list[Image.Image] = field(default_factory=list)
    lines: list = field(default_factory=list)
    backend: str = "passthrough"


class OcrBackend:
    def recognize(self, image: Image.Image, math_ocr: bool | None = None) -> OcrResult:
        raise NotImplementedError


class PassthroughOcr(OcrBackend):
    def recognize(self, image: Image.Image, math_ocr: bool | None = None) -> OcrResult:
        raise RuntimeError("图片检索需要识别文字。请填写题目文本，或改用自动识图。")


class RapidOcrBackend(OcrBackend):
    def __init__(self) -> None:
        try:
            from rapidocr import RapidOCR
        except ImportError:
            try:
                from rapidocr_onnxruntime import RapidOCR
            except ImportError as exc:
                raise RuntimeError("未安装 RapidOCR，无法从图片识题。") from exc
        self._ocr = RapidOCR()

    def recognize(self, image: Image.Image, math_ocr: bool | None = None) -> OcrResult:
        rgb = image.convert("RGB")
        raw = self._ocr(np.asarray(rgb))
        from eqsearch.vision.layout import boxes_from_rapid, extract_diagram_crops, stem_text
        from eqsearch.vision.mathocr import parse_math_ocr_flag
        from eqsearch.vision.read_question import apply_vision_read

        lines = boxes_from_rapid(raw)
        stem = stem_text(lines) or "".join(_texts_from_rapid(raw))
        use_formula = parse_math_ocr_flag(math_ocr)
        text, latex = apply_vision_read(rgb, stem, use_formula)
        crops = extract_diagram_crops(rgb, [line.box for line in lines if line.box[2] > line.box[0]])
        return OcrResult(text=text, latex=latex, diagram_crops=crops, lines=lines, backend="rapid")


class PaddleOcrBackend(OcrBackend):
    def __init__(self) -> None:
        try:
            from paddleocr import PaddleOCR
        except ImportError as exc:
            raise RuntimeError("未安装 paddleocr，无法从图片识题。") from exc
        self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)

    def recognize(self, image: Image.Image, math_ocr: bool | None = None) -> OcrResult:
        rgb = image.convert("RGB")
        result = self._ocr.ocr(np.asarray(rgb), cls=True)
        from eqsearch.vision.layout import OcrLine, extract_diagram_crops, stem_text

        lines: list[OcrLine] = []
        if result:
            for page in result:
                if not page:
                    continue
                for line in page:
                    if not line or len(line) < 2:
                        continue
                    text = str(line[1][0])
                    box = line[0]
                    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
                    x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
                    x1, y1 = int(pts[:, 0].max()), int(pts[:, 1].max())
                    lines.append(OcrLine(text=text, box=(x0, y0, x1, y1)))
        stem = stem_text(lines)
        from eqsearch.vision.mathocr import parse_math_ocr_flag
        from eqsearch.vision.read_question import apply_vision_read

        use_formula = parse_math_ocr_flag(math_ocr)
        text, latex = apply_vision_read(rgb, stem, use_formula)
        crops = extract_diagram_crops(rgb, [line.box for line in lines if line.box[2] > line.box[0]])
        return OcrResult(text=text, latex=latex, diagram_crops=crops, lines=lines, backend="paddle")


def _texts_from_rapid(result: object) -> list[str]:
    if result is None:
        return []
    txts = getattr(result, "txts", None)
    if txts:
        return [str(t) for t in txts if t]
    if isinstance(result, tuple) and result:
        result = result[0]
    lines: list[str] = []
    if isinstance(result, list):
        for item in result:
            if not item:
                continue
            if isinstance(item, str):
                lines.append(item)
                continue
            if isinstance(item, (list, tuple)):
                if len(item) >= 2 and isinstance(item[1], str):
                    lines.append(item[1])
                elif item and isinstance(item[0], str):
                    lines.append(item[0])
    return lines


_AUTO_ENGINE: OcrBackend | None = None


def get_ocr_backend(name: str | None) -> OcrBackend:
    key = (name or "auto").strip().lower()
    if key in ("none", "passthrough"):
        return PassthroughOcr()
    if key in ("auto", "rapid", "math"):
        return _auto_engine()
    if key == "paddle":
        return PaddleOcrBackend()
    raise ValueError(f"未知 OCR 后端: {name}")


def _auto_engine() -> OcrBackend:
    global _AUTO_ENGINE
    if _AUTO_ENGINE is None:
        errors: list[str] = []
        try:
            _AUTO_ENGINE = RapidOcrBackend()
            return _AUTO_ENGINE
        except Exception as exc:
            errors.append(f"RapidOCR: {exc}")
        try:
            _AUTO_ENGINE = PaddleOcrBackend()
            return _AUTO_ENGINE
        except Exception as exc:
            errors.append(f"PaddleOCR: {exc}")
        raise RuntimeError("无法启动识图引擎。请安装 rapidocr、onnxruntime。" + "；".join(errors))
    return _AUTO_ENGINE


def open_image(path: str | Path) -> Image.Image:
    return Image.open(path).convert("RGB")
