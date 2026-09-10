"""formula_10k 按数据源分目录：ape / cm17k / geometry3k / math。"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
SET_DIR = HERE / "formula_10k"
SOURCES = ("ape", "cm17k", "geometry3k", "math")
PHASES = ("text", "image")


def safe_name(item_id: str) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", str(item_id))
    return name[:180]


def source_root(source: str) -> Path:
    return SET_DIR / str(source)


def image_dir(source: str) -> Path:
    return source_root(source) / "images"


def image_path(source: str, item_id: str) -> Path:
    return image_dir(source) / f"{safe_name(item_id)}.png"


def manifest_path(source: str) -> Path:
    return source_root(source) / "manifest.jsonl"


def results_path(source: str, phase: str) -> Path:
    return source_root(source) / f"results_{phase}.jsonl"


def parse_sources(raw: str | None) -> tuple[str, ...]:
    text = (raw or "").strip()
    if not text or text == "all":
        return SOURCES
    wanted = [part.strip() for part in text.split(",") if part.strip()]
    unknown = [name for name in wanted if name not in SOURCES]
    if unknown:
        raise SystemExit(f"未知数据源：{unknown}，可选 {','.join(SOURCES)}")
    return tuple(wanted)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_source_files(source: str, rows: list[dict], extra_meta: dict | None = None) -> None:
    root = source_root(source)
    root.mkdir(parents=True, exist_ok=True)
    image_dir(source).mkdir(parents=True, exist_ok=True)
    write_jsonl(manifest_path(source), rows)
    (root / "ids.txt").write_text("\n".join(str(r["id"]) for r in rows) + "\n", encoding="utf-8")
    mapping = "\n".join(f"{safe_name(str(r['id']))}.png\t{r['id']}" for r in rows)
    (image_dir(source) / "manifest.txt").write_text(mapping + ("\n" if mapping else ""), encoding="utf-8")
    meta = {"source": source, "n": len(rows)}
    if extra_meta:
        meta.update(extra_meta)
    (root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_manifests(sources: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    maybe_migrate_flat()
    rows: list[dict] = []
    for source in sources or SOURCES:
        path = manifest_path(source)
        if not path.is_file():
            continue
        for row in _load_jsonl(path):
            row.setdefault("source", source)
            rows.append(row)
    rows.sort(key=lambda r: (str(r.get("source") or ""), str(r.get("id") or "")))
    return rows


def load_tasks(sources: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    tasks: list[dict] = []
    for row in load_manifests(sources):
        item_id = str(row["id"])
        source = str(row.get("source") or "unknown")
        tasks.append(
            {
                "id": item_id,
                "source": source,
                "kind": row.get("kind"),
                "has_diagram": bool(row.get("has_diagram")),
                "original_text": row.get("original_text") or "",
                "image": str(image_path(source, item_id)),
            }
        )
    return tasks


def load_results(phase: str, sources: tuple[str, ...] | list[str] | None = None) -> list[dict]:
    maybe_migrate_flat()
    rows: list[dict] = []
    for source in sources or SOURCES:
        rows.extend(_load_jsonl(results_path(source, phase)))
    rows.sort(key=lambda r: (str(r.get("source") or ""), str(r.get("id") or "")))
    return rows


def clear_results(phase: str, sources: tuple[str, ...] | list[str] | None = None) -> None:
    for source in sources or SOURCES:
        path = results_path(source, phase)
        if path.exists():
            path.unlink()


def _id_to_source(rows: list[dict]) -> dict[str, str]:
    return {str(row["id"]): str(row.get("source") or "unknown") for row in rows}


def maybe_migrate_flat() -> dict | None:
    """把旧的混在一起的 manifest / 图片 / 结果拆到各数据源目录。幂等。"""
    old_manifest = SET_DIR / "manifest.jsonl"
    if not old_manifest.is_file():
        return None
    rows = _load_jsonl(old_manifest)
    if not rows:
        return None

    by_src: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_src[str(row.get("source") or "unknown")].append(row)

    top_meta: dict = {}
    meta_path = SET_DIR / "meta.json"
    if meta_path.is_file():
        try:
            top_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            top_meta = {}
    quota = top_meta.get("quota") or {}

    old_images = SET_DIR / "images"
    moved_images = 0
    for source, items in by_src.items():
        extra = {"seed": top_meta.get("seed")}
        if source in quota:
            extra["quota"] = quota[source]
        write_source_files(source, items, extra_meta=extra)
        for row in items:
            src_png = old_images / f"{safe_name(str(row['id']))}.png"
            dest = image_path(source, str(row["id"]))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if src_png.is_file():
                if dest.is_file() and dest.resolve() != src_png.resolve():
                    dest.unlink()
                src_png.replace(dest)
                moved_images += 1

    lookup = _id_to_source(rows)
    for phase in PHASES:
        old = SET_DIR / f"results_{phase}.jsonl"
        if not old.is_file():
            continue
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in _load_jsonl(old):
            source = str(row.get("source") or lookup.get(str(row.get("id") or ""), "unknown"))
            row.setdefault("source", source)
            grouped[source].append(row)
        for source, items in grouped.items():
            dest = results_path(source, phase)
            if not dest.is_file():
                write_jsonl(dest, items)
        old.unlink()

    old_ids = SET_DIR / "ids.txt"
    if old_ids.is_file():
        old_ids.unlink()
    old_manifest.unlink()

    top_meta["layout"] = "by_source"
    top_meta["dirs"] = {source: source for source in by_src}
    meta_path.write_text(json.dumps(top_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    leftover = []
    if old_images.is_dir():
        for leftover_name in ("manifest.txt", "render_summary.json", "render_failed.txt"):
            path = old_images / leftover_name
            if path.is_file():
                path.unlink()
        leftover = [p.name for p in old_images.iterdir()]
        if not leftover:
            old_images.rmdir()

    summary = {
        "migrated": True,
        "sources": {source: len(items) for source, items in sorted(by_src.items())},
        "moved_images": moved_images,
        "leftover_flat_images": leftover,
    }
    print(json.dumps({"formula_10k_migrate": summary}, ensure_ascii=False), flush=True)
    return summary
