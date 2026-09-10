"""离线把 APE / CM17K / Geometry3K / Hendrycks MATH 编进向量索引。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from eqsearch.config import SearchConfig
from eqsearch.datasets.loaders import iter_json_records, iter_source_items, mwp_to_item
from eqsearch.encode import build_encoder
from eqsearch.index.gallery import Gallery, encode_gallery
from eqsearch.models import GalleryItem
from eqsearch.text.normalize import normalize_text, structure_text, variant_group_id
from eqsearch.vision.diagram import canonicalize_figure, mean_diagram_vector
from eqsearch.vision.layout import extract_diagram_crops
from eqsearch.vision.ocr import OcrBackend, open_image
from eqsearch.vision.phash import perceptual_hash


def iter_jsonl(path: Path) -> Iterator[dict]:
    yield from iter_json_records(path)


def ape_to_item(raw: dict) -> GalleryItem:
    return mwp_to_item(raw, source="ape")


def image_to_item(item_id: str, image_path: Path, ocr: OcrBackend) -> GalleryItem:
    image = open_image(image_path)
    ocr_result = ocr.recognize(image)
    text = ocr_result.text
    structure = structure_text(text)
    crops = list(ocr_result.diagram_crops) or extract_diagram_crops(image, [])
    return GalleryItem(
        id=item_id,
        original_text=text,
        normalized_text=normalize_text(text),
        structure_text=structure,
        phash=perceptual_hash(canonicalize_figure(crops[0])) if crops else None,
        diagram_vector=mean_diagram_vector(crops),
        original_cluster_id=item_id,
        variant_group_id=variant_group_id(structure),
        meta={"image": str(image_path), "ocr": ocr_result.backend, "has_diagram": bool(crops)},
    )


def ingest_records(
    records: Iterable[GalleryItem],
    encoder_kind: str = "tfidf",
    config: SearchConfig | None = None,
) -> Gallery:
    items = [item for item in records if item.normalized_text]
    if not items:
        raise ValueError("没有可入库的题目")
    config = config or SearchConfig()
    encoder = build_encoder(encoder_kind)
    index = encode_gallery(items, encoder, config)
    return Gallery(items=items, index=index, encoder=encoder, config=config)


def ingest_ape(path: Path, limit: int | None = None, encoder_kind: str = "tfidf") -> Gallery:
    return ingest_source(path, source="ape", limit=limit, encoder_kind=encoder_kind)


def ingest_source(
    path: Path,
    source: str | None = None,
    limit: int | None = None,
    encoder_kind: str = "tfidf",
) -> Gallery:
    items = list(iter_source_items(path, source=source, limit=limit))
    return ingest_records(items, encoder_kind=encoder_kind)


def ingest_sources(
    specs: list[tuple[Path, str | None]],
    limit: int | None = None,
    encoder_kind: str = "tfidf",
) -> Gallery:
    items: list[GalleryItem] = []
    seen: set[str] = set()
    remaining = limit
    for path, source in specs:
        for item in iter_source_items(path, source=source, limit=remaining):
            if item.id in seen:
                continue
            seen.add(item.id)
            items.append(item)
            if remaining is not None:
                remaining -= 1
                if remaining <= 0:
                    return ingest_records(items, encoder_kind=encoder_kind)
    return ingest_records(items, encoder_kind=encoder_kind)
