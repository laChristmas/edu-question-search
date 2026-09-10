"""开源视觉模型整图读题（含公式 LaTeX）。公式检测开时用它，不再裁块跑 RapidLaTeXOCR。"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import threading
from dataclasses import dataclass

from PIL import Image

from eqsearch.text.formula import formula_template_blob

_PROMPT = (
    "请只抄写图片中的题目正文。数学公式用 LaTeX，写在 $...$ 中。"
    "不要解题，不要描述背景、手指、桌面或配图。看不清的字符不要编造。"
)
_FENCE = re.compile(r"^```(?:markdown|tex|latex|text)?\s*|\s*```$", re.I | re.M)
_PREFIX = re.compile(r"^(?:题目|问题|题干|Question|Problem)\s*[:：]\s*", re.I)
_SOLVE = re.compile(r"^(?:解答|答案|解析|解[:：]|Answer|Solution)\b", re.I)
_PAREN = re.compile(r"\\\((.+?)\\\)", re.S)
_BRACKET = re.compile(r"\\\[(.+?)\\\]", re.S)

_LOG = logging.getLogger(__name__)
_KIND: str | None = None
_READER = None
_READER_FAILED = False
_QWEN_MODEL = os.environ.get("EQSEARCH_QWEN_VL", "Qwen/Qwen2.5-VL-3B-Instruct")
_PREDICT_LOCK = threading.Lock()


@dataclass
class ReadResult:
    text: str = ""
    latex: str = ""
    backend: str = ""


def parse_vision_reader_kind(value: str | None = None) -> str:
    raw = (value if value is not None else os.environ.get("EQSEARCH_VISION_READER") or "auto").strip().lower()
    if raw in {"0", "false", "off", "no", "none", "n"}:
        return "off"
    if raw in {"paddle", "paddleocr", "paddleocr-vl", "ppocr-vl"}:
        return "paddleocr-vl"
    if raw in {"qwen", "qwen-vl", "qwen2.5-vl"}:
        return "qwen"
    return "auto"


def vision_reader_available() -> bool:
    if parse_vision_reader_kind() == "off":
        return False
    if _READER_FAILED:
        return False
    if _READER is not None:
        return True
    return _first_importable_kind() is not None


def formula_engine_available() -> bool:
    """兼容旧接口：公式检测用的读图模型是否可用。"""
    return vision_reader_available()


def vl_max_side() -> int:
    raw = os.environ.get("EQSEARCH_VL_MAX_SIDE", "1024")
    try:
        return max(256, int(raw))
    except ValueError:
        return 1024


def fit_vl_image(image: Image.Image, max_side: int | None = None) -> Image.Image:
    """缩小长边，避免手机原图把 6GB 显存打满后卡死。"""
    rgb = image.convert("RGB")
    limit = vl_max_side() if max_side is None else max_side
    width, height = rgb.size
    longest = max(width, height)
    if longest <= limit:
        return rgb
    scale = limit / float(longest)
    size = (max(32, int(width * scale)), max(32, int(height * scale)))
    return rgb.resize(size, Image.Resampling.BILINEAR)


def warmup_vision_reader() -> None:
    """服务启动时加载读图模型，避免第一次检索卡在加载权重。"""
    if parse_vision_reader_kind() == "off":
        return
    if not vision_reader_available():
        return
    blank = Image.new("RGB", (64, 32), "white")
    read_question_image(blank)


def apply_vision_read(image: Image.Image, stem_text: str, enabled: bool) -> tuple[str, str]:
    """公式检测开时用整图读题替换题干；失败则退回文字 OCR 题干。"""
    if not enabled:
        return stem_text, ""
    read = read_question_image(image)
    if read.text.strip():
        return read.text.strip(), read.latex
    return stem_text, ""


def read_question_image(image: Image.Image) -> ReadResult:
    reader = _engine()
    if reader is None:
        return ReadResult()
    rgb = image.convert("RGB")
    try:
        raw, backend = reader(rgb)
    except Exception:
        return ReadResult()
    text = clean_reader_text(raw)
    latex = formula_template_blob(text) or ""
    return ReadResult(text=text, latex=latex, backend=backend)


def clean_reader_text(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    text = _FENCE.sub("", text).strip()
    text = _PAREN.sub(lambda m: f"${m.group(1).strip()}$", text)
    text = _BRACKET.sub(lambda m: f"${m.group(1).strip()}$", text)
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _SOLVE.match(stripped):
            break
        stripped = _PREFIX.sub("", stripped)
        if stripped:
            lines.append(stripped)
    return re.sub(r"[ \t]+", " ", " ".join(lines)).strip()


def _engine():
    global _KIND, _READER, _READER_FAILED
    if _READER_FAILED:
        return None
    if _READER is not None:
        return _READER
    kind = parse_vision_reader_kind()
    order = ["paddleocr-vl", "qwen"] if kind == "auto" else [kind]
    last_error: Exception | None = None
    for name in order:
        if name == "off":
            break
        try:
            loaded = _load_backend(name)
        except Exception as exc:
            last_error = exc
            continue
        if loaded is None:
            continue
        _KIND = name
        _READER = loaded
        return _READER
    _READER_FAILED = True
    if last_error is not None:
        return None
    return None


def _first_importable_kind() -> str | None:
    kind = parse_vision_reader_kind()
    order = ["paddleocr-vl", "qwen"] if kind == "auto" else [kind]
    for name in order:
        if name == "paddleocr-vl" and _paddleocr_vl_importable():
            return name
        if name == "qwen" and _qwen_importable():
            return name
    return None


def _paddleocr_vl_importable() -> bool:
    try:
        from paddleocr import PaddleOCRVL  # noqa: F401

        return True
    except Exception:
        return False


def _qwen_importable() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import AutoProcessor  # noqa: F401

        return True
    except Exception:
        return False


def _load_backend(name: str):
    if name == "paddleocr-vl":
        return _load_paddleocr_vl()
    if name == "qwen":
        return _load_qwen()
    return None


def _load_paddleocr_vl():
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "bos")
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(use_doc_unwarping=False, use_layout_detection=False)

    def _run(image: Image.Image) -> tuple[str, str]:
        fitted = fit_vl_image(image)
        _LOG.info("PaddleOCR-VL 读图 %sx%s -> %sx%s", *image.size, *fitted.size)
        path = _temp_png(fitted)
        try:
            with _PREDICT_LOCK:
                output = pipeline.predict(path)
        finally:
            _remove(path)
        text = ""
        if output:
            text = _paddle_vl_to_text(output[0])
        return text, "paddleocr-vl"

    return _run


def _load_qwen():
    import torch
    from transformers import AutoProcessor

    try:
        from transformers import Qwen2_5_VLForConditionalGeneration as VLModel
    except ImportError:
        from transformers import Qwen2VLForConditionalGeneration as VLModel

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    model = VLModel.from_pretrained(
        _QWEN_MODEL,
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
    )
    if device != "cuda":
        model = model.to(device)
    model.eval()
    processor = AutoProcessor.from_pretrained(_QWEN_MODEL)

    def _run(image: Image.Image) -> tuple[str, str]:
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ]
        try:
            from qwen_vl_utils import process_vision_info

            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            images, videos = process_vision_info(messages)
            inputs = processor(text=[text], images=images, videos=videos, padding=True, return_tensors="pt")
        except Exception:
            inputs = processor(images=image, text=_PROMPT, return_tensors="pt")
        inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=512)
        trimmed = out[:, inputs["input_ids"].shape[1] :]
        decoded = processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        return decoded, "qwen"

    return _run


def _paddle_vl_to_text(res: object) -> str:
    if res is None:
        return ""
    markdown = getattr(res, "markdown", None)
    if callable(markdown):
        try:
            markdown = markdown()
        except Exception:
            markdown = None
    md_text = _markdown_dict_text(markdown)
    if md_text:
        return md_text
    data: object = res
    if hasattr(res, "json") and not isinstance(res, dict):
        try:
            data = res.json
        except Exception:
            data = res
    if isinstance(data, dict):
        inner = data.get("res", data)
        if not isinstance(inner, dict):
            inner = data
        md_text = _markdown_dict_text(inner.get("markdown") or inner)
        if md_text:
            return md_text
        parts = _block_texts(inner.get("parsing_res_list") or inner.get("parsing_result") or [])
        if parts:
            return "\n".join(parts)
        rec = inner.get("rec_texts") or inner.get("rec_text")
        if isinstance(rec, list):
            joined = " ".join(str(x) for x in rec if x)
            if joined.strip():
                return joined
        if isinstance(rec, str) and rec.strip():
            return rec
    if hasattr(res, "get"):
        parts = _block_texts(res.get("parsing_res_list") or [])
        if parts:
            return "\n".join(parts)
    if isinstance(res, str) and res.strip() and not res.lstrip().startswith("{"):
        return res
    return ""


def _markdown_dict_text(markdown: object) -> str:
    if isinstance(markdown, str) and markdown.strip() and not markdown.lstrip().startswith("{"):
        return markdown.strip()
    if not isinstance(markdown, dict):
        return ""
    texts = markdown.get("markdown_texts")
    if isinstance(texts, str) and texts.strip():
        return texts.strip()
    if isinstance(texts, list):
        joined = "\n".join(str(x).strip() for x in texts if str(x).strip())
        if joined:
            return joined
    for key in ("markdown", "markdown_text", "md", "text"):
        value = markdown.get(key)
        if isinstance(value, str) and value.strip() and not value.lstrip().startswith("{"):
            return value.strip()
    return ""


def _block_texts(blocks: object) -> list[str]:
    if not isinstance(blocks, list):
        return []
    parts: list[str] = []
    skip = {"image", "figure", "chart", "header", "footer", "footnote", "number"}
    for block in blocks:
        label = ""
        content = ""
        if isinstance(block, dict):
            label = str(block.get("block_label") or block.get("label") or "")
            raw = block.get("block_content") or block.get("content") or ""
            content = raw if isinstance(raw, str) else str(raw or "")
        else:
            label = str(getattr(block, "label", "") or getattr(block, "block_label", "") or "")
            raw = getattr(block, "content", None) or getattr(block, "block_content", None) or ""
            content = raw if isinstance(raw, str) else str(raw or "")
        if label.lower() in skip:
            continue
        if content.strip():
            parts.append(content.strip())
    return parts


def _temp_png(image: Image.Image) -> str:
    handle, path = tempfile.mkstemp(suffix=".png")
    os.close(handle)
    image.convert("RGB").save(path, format="PNG")
    return path


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
