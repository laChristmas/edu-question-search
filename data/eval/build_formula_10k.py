"""从当前索引分层抽出 10000 条，写成 formula_10k 测试集。不渲染、不检索。"""

from __future__ import annotations

import json
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from formula_set import SET_DIR as OUT
from formula_set import SOURCES, write_source_files

ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "data" / "index" / "items.jsonl"

SEED = 0
QUOTA = {
    "ape": 1328,
    "cm17k": 4554,
    "geometry3k": 797,
    "math": 3321,
}


def _row(obj: dict) -> dict:
    meta = obj.get("meta") or {}
    image = meta.get("image")
    has_diagram = bool(obj.get("phash") or obj.get("diagram_vector") or image)
    return {
        "id": obj["id"],
        "source": meta.get("source"),
        "kind": meta.get("kind"),
        "type": meta.get("type"),
        "split": meta.get("split"),
        "level": meta.get("level"),
        "has_diagram": has_diagram,
        "image": image,
        "original_text": obj.get("original_text") or "",
    }


def _counts(rows: list[dict]) -> dict:
    src = Counter(r["source"] for r in rows)
    kind = Counter(r["kind"] for r in rows)
    fig = Counter("yes" if r["has_diagram"] else "no" for r in rows)
    math_rows = [r for r in rows if r["source"] == "math"]
    return {
        "n": len(rows),
        "source": dict(src),
        "kind": dict(kind),
        "has_diagram": dict(fig),
        "math_type": dict(Counter(r["type"] for r in math_rows)),
        "math_split": dict(Counter(r["split"] for r in math_rows)),
        "math_level": dict(Counter(r["level"] for r in math_rows)),
        "geometry3k_split": dict(Counter(r["split"] for r in rows if r["source"] == "geometry3k")),
    }


def main() -> None:
    by_src: dict[str, list[dict]] = {key: [] for key in QUOTA}
    with ITEMS.open(encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            source = (obj.get("meta") or {}).get("source")
            if source in by_src:
                by_src[source].append(obj)
    missing = [key for key, need in QUOTA.items() if len(by_src[key]) < need]
    if missing:
        raise SystemExit(f"索引条数不足：{missing}")

    rng = random.Random(SEED)
    picked: list[dict] = []
    for source, need in QUOTA.items():
        pool = list(by_src[source])
        rng.shuffle(pool)
        picked.extend(pool[:need])
    rows = [_row(obj) for obj in picked]
    rows.sort(key=lambda r: (str(r["source"]), str(r["id"])))

    OUT.mkdir(parents=True, exist_ok=True)
    by_out: dict[str, list[dict]] = {key: [] for key in SOURCES}
    for row in rows:
        source = str(row.get("source") or "")
        if source in by_out:
            by_out[source].append(row)
    for source in SOURCES:
        write_source_files(source, by_out[source], extra_meta={"seed": SEED, "quota": QUOTA.get(source)})
    meta = {
        "name": "formula_10k",
        "seed": SEED,
        "quota": QUOTA,
        "layout": "by_source",
        "dirs": {source: source for source in SOURCES},
        "index": str(ITEMS),
        "sampling": "stratified_by_source",
        "purpose": "Render stems to images, then search with formula detection on.",
        "counts": _counts(rows),
    }
    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} items -> {OUT} ({', '.join(f'{k}={len(v)}' for k, v in by_out.items())})")


if __name__ == "__main__":
    main()
