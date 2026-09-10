"""题库：条目 JSONL、向量索引，以及展示用题干/配图路径。"""

from __future__ import annotations

import json
from pathlib import Path

from eqsearch.encode import load_encoder
from eqsearch.index.vector_index import VectorIndex, blend_visual, item_visuals
from eqsearch.models import GalleryItem
from eqsearch.config import SearchConfig

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def item_image_path(item: GalleryItem) -> Path | None:
    """入库时写入的本地配图路径；文件不存在则视为无图。"""
    raw = item.meta.get("image")
    if not raw:
        return None
    path = Path(str(raw))
    if path.suffix.lower() not in _IMAGE_SUFFIXES or not path.is_file():
        return None
    return path


def item_stem_text(item: GalleryItem) -> str:
    """返回原始题干，不用 logic form 索引文本。"""
    stored = item.meta.get("stem")
    if isinstance(stored, str) and stored.strip():
        return " ".join(stored.split())
    raw_path = item.meta.get("image")
    if raw_path:
        data_file = Path(str(raw_path)).parent / "data.json"
        if data_file.is_file():
            try:
                payload = json.loads(data_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                from eqsearch.datasets.loaders import geometry_stem

                stem = geometry_stem(payload)
                if stem:
                    return stem
    return " ".join((item.original_text or "").split())


class Gallery:
    """内存题库：items 与向量下标一一对应。"""

    def __init__(
        self,
        items: list[GalleryItem],
        index,
        encoder,
        config: SearchConfig | None = None,
    ) -> None:
        self.items = items
        self.index = index
        self.encoder = encoder
        self.config = config or SearchConfig()
        self._by_id = {item.id: item for item in items}

    def get(self, item_id: str) -> GalleryItem | None:
        return self._by_id.get(item_id)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        with (path / "items.jsonl").open("w", encoding="utf-8") as fh:
            for item in self.items:
                fh.write(item.model_dump_json() + "\n")
        self.index.save(path)
        self.encoder.save(path)
        (path / "meta.json").write_text(
            json.dumps(
                {
                    "size": len(self.items),
                    "recall_k": self.config.recall_k,
                    "sources": _source_counts(self.items),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, config: SearchConfig | None = None) -> Gallery:
        items = [
            GalleryItem.model_validate_json(line)
            for line in (path / "items.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        encoder = load_encoder(path)
        index = VectorIndex.load(path)
        return cls(items=items, index=index, encoder=encoder, config=config or SearchConfig())


def encode_gallery(items: list[GalleryItem], encoder, config: SearchConfig) -> VectorIndex:
    texts = [item.structure_text for item in items]
    encoder.fit(texts)
    encoded = encoder.encode(texts)
    blended = blend_visual(encoded, item_visuals(items), config.visual_blend)
    return VectorIndex(blended)


def _source_counts(items: list[GalleryItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.meta.get("source") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts
