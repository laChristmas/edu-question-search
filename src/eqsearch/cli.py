"""命令行：入库、下载数据、检索、评估、启动 HTTP 服务。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eqsearch.config import SearchConfig
from eqsearch.datasets.fetch import DATASETS, fetch_dataset
from eqsearch.index.gallery import Gallery, item_stem_text
from eqsearch.pipeline.ingest import ingest_ape, ingest_sources
from eqsearch.pipeline.search import search, search_image_path
from eqsearch.pipeline.eval_metrics import run_eval, run_image_eval
from eqsearch.vision.ocr import get_ocr_backend


def _print_response(resp) -> None:
    print(f"query: {resp.query_text}")
    print(
        f"recalled={resp.recalled} originals={resp.originals} "
        f"reranked={resp.reranked} returned={len(resp.results)}"
    )
    if not resp.results:
        print("results: (empty)")
        return
    for i, cand in enumerate(resp.results, 1):
        snippet = item_stem_text(cand.item)[:80]
        source = cand.item.meta.get("source") or ""
        kind = cand.item.meta.get("kind") or ""
        extra = " ".join(part for part in (source, kind) if part)
        print(
            f"{i}. id={cand.item.id} relation={cand.relation} "
            f"final={cand.final_score:.3f} surface={cand.surface:.3f} structure={cand.structure:.3f}"
            + (f" {extra}" if extra else "")
        )
        print(f"   {snippet}")


def _ingest_specs(args: argparse.Namespace) -> list[tuple[Path, str | None]]:
    specs: list[tuple[Path, str | None]] = []
    if args.ape:
        specs.append((Path(args.ape), "ape"))
    if args.cm17k:
        specs.append((Path(args.cm17k), "cm17k"))
    if args.geometry3k:
        specs.append((Path(args.geometry3k), "geometry3k"))
    if args.math:
        specs.append((Path(args.math), "math"))
    source = None if args.source == "auto" else args.source
    for raw in args.input or []:
        specs.append((Path(raw), source))
    return specs


def cmd_ingest(args: argparse.Namespace) -> None:
    specs = _ingest_specs(args)
    if not specs:
        raise SystemExit("请提供 --input，或 --ape / --cm17k / --geometry3k / --math")
    if len(specs) == 1 and specs[0][1] == "ape":
        gallery = ingest_ape(specs[0][0], limit=args.limit, encoder_kind=args.encoder)
    else:
        gallery = ingest_sources(specs, limit=args.limit, encoder_kind=args.encoder)
    out = Path(args.out)
    gallery.save(out)
    sources = {}
    for item in gallery.items:
        key = str(item.meta.get("source") or "unknown")
        sources[key] = sources.get(key, 0) + 1
    print(f"ingested {len(gallery.items)} items -> {out} {sources}")


def cmd_fetch(args: argparse.Namespace) -> None:
    dest = Path(args.out) if args.out else Path("data/raw") / args.dataset
    splits = tuple(s.strip() for s in args.splits.split(",") if s.strip()) or None
    path = fetch_dataset(args.dataset, dest, splits=splits)
    print(f"fetched {args.dataset} -> {path}")


def cmd_search(args: argparse.Namespace) -> None:
    gallery = Gallery.load(Path(args.index), SearchConfig())
    ocr = get_ocr_backend(args.ocr) if args.image else None
    if args.image:
        resp = search_image_path(
            gallery,
            Path(args.image),
            ocr=ocr,
            extra_text=args.text or "",
            math_ocr=args.math_ocr,
        )
    else:
        if not args.text:
            raise SystemExit("请提供 --text 或 --image")
        resp = search(gallery, text=args.text, math_ocr=args.math_ocr)
    if args.json:
        print(resp.model_dump_json(indent=2, ensure_ascii=False))
    else:
        _print_response(resp)


def cmd_eval(args: argparse.Namespace) -> None:
    gallery = Gallery.load(Path(args.index), SearchConfig())
    report: dict = {"text": run_eval(gallery, limit=args.limit, seed=args.seed, math_ocr=args.math_ocr)}
    if args.images:
        ocr = get_ocr_backend(args.ocr)
        report["image"] = run_image_eval(
            gallery,
            Path(args.images),
            ocr=ocr,
            math_ocr=args.math_ocr,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def cmd_serve(args: argparse.Namespace) -> None:
    import os

    import uvicorn

    os.environ["EQSEARCH_INDEX"] = str(Path(args.index).resolve())
    uvicorn.run("eqsearch.api.app:app", host=args.host, port=args.port, reload=False)


def main() -> None:
    parser = argparse.ArgumentParser(prog="eqsearch", description="变式题检索：返回原题和变式，最多 3 张")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ing = sub.add_parser("ingest", help="离线入库")
    p_ing.add_argument("--input", action="append", default=[], help="自动识别或配合 --source")
    p_ing.add_argument("--source", default="auto", choices=["auto", "ape", "cm17k", "geometry3k", "math"])
    p_ing.add_argument("--ape", default="", help="APE JSONL")
    p_ing.add_argument("--cm17k", default="", help="CM17K JSON 或目录")
    p_ing.add_argument("--geometry3k", default="", help="Geometry3K 题目目录")
    p_ing.add_argument("--math", default="", help="Hendrycks MATH JSON / JSONL 或目录")
    p_ing.add_argument("--out", default="data/index")
    p_ing.add_argument("--limit", type=int, default=None)
    p_ing.add_argument("--encoder", default="tfidf", choices=["tfidf", "sbert"])
    p_ing.set_defaults(func=cmd_ingest)

    p_f = sub.add_parser("fetch", help="下载 CM17K / Geometry3K / Hendrycks MATH")
    p_f.add_argument("dataset", choices=list(DATASETS))
    p_f.add_argument("--out", default="")
    p_f.add_argument("--splits", default="train,val,test", help="Geometry3K 为 train,val,test；MATH 为 train,test")
    p_f.set_defaults(func=cmd_fetch)

    p_s = sub.add_parser("search", help="在线查询")
    p_s.add_argument("--index", default="data/index")
    p_s.add_argument("--text", default="")
    p_s.add_argument("--image", default="")
    p_s.add_argument("--ocr", default="auto", help="auto/rapid 识题干；paddle 需另装")
    p_s.add_argument("--math-ocr", action=argparse.BooleanOptionalAction, default=True, help="公式检测：开源模型整图读题后再比题干∧公式∧附图；--no-math-ocr 只比题干和附图")
    p_s.add_argument("--json", action="store_true")
    p_s.set_defaults(func=cmd_search)

    p_e = sub.add_parser("eval", help="自动测原题命中率 / 首位命中 / 误标原题")
    p_e.add_argument("--index", default="data/index")
    p_e.add_argument("--limit", type=int, default=200)
    p_e.add_argument("--seed", type=int, default=0)
    p_e.add_argument("--images", default="", help="题目图片目录；有 manifest.txt 则按 文件名\\t题目id 对齐")
    p_e.add_argument("--ocr", default="auto")
    p_e.add_argument(
        "--math-ocr",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="评估时是否走公式检测；--no-math-ocr 只比题干和附图",
    )
    p_e.set_defaults(func=cmd_eval)

    p_v = sub.add_parser("serve", help="启动 HTTP 服务")
    p_v.add_argument("--index", default="data/index")
    p_v.add_argument("--host", default="127.0.0.1")
    p_v.add_argument("--port", type=int, default=8000)
    p_v.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
