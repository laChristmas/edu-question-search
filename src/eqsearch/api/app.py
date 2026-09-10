"""HTTP 服务：检索页、JSON 接口、题目配图。"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from io import BytesIO
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from eqsearch.config import SearchConfig
from eqsearch.index.gallery import Gallery, item_image_path, item_stem_text
from eqsearch.pipeline.search import search
from eqsearch.vision.mathocr import parse_math_ocr_flag
from eqsearch.vision.ocr import get_ocr_backend

INDEX_ENV = "EQSEARCH_INDEX"
STATIC_DIR = Path(__file__).resolve().parent / "static"
_gallery: Gallery | None = None
_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


def _image_url(item) -> str | None:
    if item_image_path(item) is None:
        return None
    return f"/v1/items/{quote(item.id, safe='')}/image"


def _result_payload(c, use_formula: bool = True) -> dict:
    """对外 JSON：text 为原始题干，image 为配图 URL（无图则为 null）。"""
    return {
        "id": c.item.id,
        "text": item_stem_text(c.item),
        "relation": c.relation,
        "source": c.item.meta.get("source"),
        "kind": c.item.meta.get("kind"),
        "image": _image_url(c.item),
        "final_score": round(c.final_score, 4),
        "surface": round(c.surface, 4),
        "structure": round(c.structure, 4),
        "formula": round(c.formula_score, 4) if use_formula else None,
        "diagram": None if c.diagram_score is None else round(c.diagram_score, 4),
    }


def get_gallery() -> Gallery:
    global _gallery
    if _gallery is None:
        path = Path(os.environ.get(INDEX_ENV, "data/index"))
        _gallery = Gallery.load(path, SearchConfig())
    return _gallery


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = os.environ.get(INDEX_ENV)
    if path and Path(path).exists():
        get_gallery()
    try:
        from eqsearch.vision.read_question import warmup_vision_reader

        warmup_vision_reader()
    except Exception:
        pass
    yield


app = FastAPI(title="eqsearch", lifespan=lifespan)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    gallery = get_gallery()
    sources: dict[str, int] = {}
    for item in gallery.items:
        key = str(item.meta.get("source") or "unknown")
        sources[key] = sources.get(key, 0) + 1
    return {"ok": True, "items": len(gallery.items), "sources": sources}


@app.post("/v1/search")
async def search_endpoint(
    text: str = Form(default=""),
    ocr: str = Form(default="auto"),
    math_ocr: str = Form(default=""),
    image: UploadFile | None = File(default=None),
) -> dict:
    """以文本和/或题目图片检索。原题优先，最多 3 条。"""
    gallery = get_gallery()
    pil = None
    backend = None
    use_math = parse_math_ocr_flag(math_ocr)
    if image is not None and image.filename:
        raw = await image.read()
        if raw:
            try:
                pil = Image.open(BytesIO(raw)).convert("RGB")
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"无法读取图片：{exc}") from exc
    try:
        if pil is not None:
            backend = await asyncio.to_thread(get_ocr_backend, ocr or "auto")
        resp = await asyncio.to_thread(
            search, gallery, text=text, image=pil, ocr=backend, math_ocr=use_math
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "query_text": resp.query_text,
        "has_diagram": resp.has_diagram,
        "math_ocr": resp.math_ocr,
        "formula_engine": resp.formula_engine,
        "originals": resp.originals,
        "recalled": resp.recalled,
        "reranked": resp.reranked,
        "results": [_result_payload(c, use_formula=resp.math_ocr) for c in resp.results],
    }


@app.get("/v1/items/{item_id}/image")
def item_image(item_id: str):
    """返回题库中该题的本地配图，路径来自入库时的 meta.image。"""
    gallery = get_gallery()
    item = gallery.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="题目不存在")
    path = item_image_path(item)
    if path is None:
        raise HTTPException(status_code=404, detail="该题没有图片")
    media = _IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(path, media_type=media)
