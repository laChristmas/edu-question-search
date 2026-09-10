"""自动测成功率：文本金标回灌，可选题目图片。"""

from __future__ import annotations

import random
import re
from pathlib import Path

from eqsearch.index.gallery import Gallery
from eqsearch.pipeline.search import search
from eqsearch.vision.ocr import OcrBackend, open_image

_NUM = re.compile(r"\d+(?:\.\d+)?%?")


def substitute_numbers(text: str) -> str | None:
    if not _NUM.search(text):
        return None

    def repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        if raw.endswith("%"):
            value = float(raw[:-1])
            nxt = (value + 17) % 90 + 5
            if "." in raw:
                return f"{nxt:.1f}%"
            return f"{int(nxt)}%"
        if "." in raw:
            return f"{float(raw) + 1.7:.1f}"
        n = int(raw)
        return str(n + 13)

    out = _NUM.sub(repl, text)
    return out if out != text else None


def score_response(resp, gold_id: str) -> dict:
    ids = [c.item.id for c in resp.results]
    original_ids = [c.item.id for c in resp.results if c.is_original]
    return {
        "hit": gold_id in ids,
        "first": bool(ids) and ids[0] == gold_id,
        "gold_original": gold_id in original_ids,
        "extra_originals": sum(1 for item_id in original_ids if item_id != gold_id),
        "empty": not ids,
        "returned": len(ids),
    }


def _aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "samples": 0,
            "hit_rate": 0.0,
            "first_rate": 0.0,
            "gold_original_rate": 0.0,
            "extra_original_rate": 0.0,
            "empty_rate": 0.0,
            "avg_returned": 0.0,
        }
    return {
        "samples": n,
        "hit_rate": sum(r["hit"] for r in rows) / n,
        "first_rate": sum(r["first"] for r in rows) / n,
        "gold_original_rate": sum(r["gold_original"] for r in rows) / n,
        "extra_original_rate": sum(1 for r in rows if r["extra_originals"] > 0) / n,
        "empty_rate": sum(r["empty"] for r in rows) / n,
        "avg_returned": sum(r["returned"] for r in rows) / n,
    }


def run_eval(
    gallery: Gallery,
    limit: int = 200,
    seed: int = 0,
    math_ocr: bool | None = None,
) -> dict:
    rng = random.Random(seed)
    items = list(gallery.items)
    rng.shuffle(items)
    items = items[:limit]
    original_rows: list[dict] = []
    variant_hits = 0
    variant_denom = 0

    for item in items:
        original_resp = search(gallery, text=item.original_text, math_ocr=math_ocr)
        original_rows.append(score_response(original_resp, item.id))
        variant_text = substitute_numbers(item.original_text)
        if not variant_text:
            continue
        variant_denom += 1
        variant_resp = search(gallery, text=variant_text, math_ocr=math_ocr)
        if any(c.item.id == item.id for c in variant_resp.results):
            variant_hits += 1

    text_report = _aggregate(original_rows)
    return {
        "samples": text_report["samples"],
        "original_hit_rate": text_report["hit_rate"],
        "original_first_rate": text_report["first_rate"],
        "gold_marked_original_rate": text_report["gold_original_rate"],
        "false_extra_original_rate": text_report["extra_original_rate"],
        "original_empty_rate": text_report["empty_rate"],
        "variant_recall_at_3": variant_hits / variant_denom if variant_denom else 0.0,
        "variant_samples": variant_denom,
        "avg_returned_on_original_query": text_report["avg_returned"],
        "max_returned": max((r["returned"] for r in original_rows), default=0),
    }


def parse_image_manifest(folder: Path) -> list[tuple[Path, str]]:
    """manifest.txt：每行 `文件名\\t题目id`；没有清单则跳过无法对应 id 的图。"""
    folder = Path(folder)
    manifest = folder / "manifest.txt"
    pairs: list[tuple[Path, str]] = []
    if manifest.is_file():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            path = folder / parts[0].strip()
            gold_id = parts[1].strip()
            if path.is_file() and gold_id:
                pairs.append((path, gold_id))
        return pairs
    for path in sorted(folder.glob("*.png")):
        gold_id = path.stem
        pairs.append((path, gold_id))
    return pairs


def run_image_eval(
    gallery: Gallery,
    folder: Path,
    ocr: OcrBackend,
    math_ocr: bool | None = None,
) -> dict:
    known = {item.id for item in gallery.items}
    rows: list[dict] = []
    skipped = 0
    for path, gold_id in parse_image_manifest(folder):
        if gold_id not in known:
            skipped += 1
            continue
        image = open_image(path)
        resp = search(gallery, image=image, ocr=ocr, math_ocr=math_ocr)
        rows.append(score_response(resp, gold_id))
    report = _aggregate(rows)
    report["skipped_unknown_id"] = skipped
    return report
