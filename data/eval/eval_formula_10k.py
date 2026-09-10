"""评测 formula_10k。默认公式检测开；--no-math-ocr 只比题干和附图。可断点续跑。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eqsearch.config import SearchConfig
from eqsearch.index.gallery import Gallery
from eqsearch.pipeline.eval_metrics import score_response
from eqsearch.pipeline.search import search
from eqsearch.vision.ocr import get_ocr_backend, open_image
from formula_set import (
    SET_DIR,
    SOURCES,
    clear_results,
    load_results,
    load_tasks,
    parse_sources,
    results_path,
    source_root,
)

INDEX = ROOT / "data" / "index"
TEXT_GOLD_LAST = SET_DIR / "text_gold_last.json"


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        fh.flush()


def pack_results(resp) -> list[dict]:
    out = []
    for cand in resp.results:
        out.append(
            {
                "id": cand.item.id,
                "relation": cand.relation,
                "final": round(float(cand.final_score), 4),
                "surface": round(float(cand.surface), 4),
                "structure": round(float(cand.structure), 4),
                "formula": round(float(cand.formula_score), 4),
            }
        )
    return out


def empty_row(task: dict, phase: str, error: str, elapsed: float, math_ocr: bool) -> dict:
    return {
        "id": task["id"],
        "source": task["source"],
        "kind": task["kind"],
        "has_diagram": task["has_diagram"],
        "phase": phase,
        "hit": False,
        "first": False,
        "gold_original": False,
        "extra_originals": 0,
        "empty": True,
        "returned": 0,
        "query_text": "",
        "results": [],
        "error": error,
        "elapsed_s": round(elapsed, 3),
        "math_ocr": math_ocr,
    }


def scored_row(task: dict, phase: str, resp, elapsed: float, math_ocr: bool) -> dict:
    score = score_response(resp, task["id"])
    return {
        "id": task["id"],
        "source": task["source"],
        "kind": task["kind"],
        "has_diagram": task["has_diagram"],
        "phase": phase,
        **score,
        "query_text": (resp.query_text or "")[:400],
        "results": pack_results(resp),
        "error": "",
        "elapsed_s": round(elapsed, 3),
        "math_ocr": bool(getattr(resp, "math_ocr", math_ocr)),
    }


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        return {
            "samples": 0,
            "hit": 0,
            "first": 0,
            "gold_original": 0,
            "extra_original": 0,
            "empty": 0,
            "hit_rate": 0.0,
            "first_rate": 0.0,
            "gold_original_rate": 0.0,
            "extra_original_rate": 0.0,
            "empty_rate": 0.0,
            "avg_returned": 0.0,
            "avg_elapsed_s": 0.0,
        }
    extra = sum(1 for r in rows if r.get("extra_originals", 0) > 0)
    return {
        "samples": n,
        "hit": sum(bool(r.get("hit")) for r in rows),
        "first": sum(bool(r.get("first")) for r in rows),
        "gold_original": sum(bool(r.get("gold_original")) for r in rows),
        "extra_original": extra,
        "empty": sum(bool(r.get("empty")) for r in rows),
        "hit_rate": sum(bool(r.get("hit")) for r in rows) / n,
        "first_rate": sum(bool(r.get("first")) for r in rows) / n,
        "gold_original_rate": sum(bool(r.get("gold_original")) for r in rows) / n,
        "extra_original_rate": extra / n,
        "empty_rate": sum(bool(r.get("empty")) for r in rows) / n,
        "avg_returned": sum(int(r.get("returned") or 0) for r in rows) / n,
        "avg_elapsed_s": sum(float(r.get("elapsed_s") or 0) for r in rows) / n,
    }


def by_key(rows: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        groups[str(row.get(key) or "unknown")].append(row)
    return {name: summarize(items) for name, items in sorted(groups.items())}


def failure_samples(rows: list[dict], limit: int = 30) -> dict[str, list[dict]]:
    def brief(row: dict) -> dict:
        return {
            "id": row["id"],
            "source": row.get("source"),
            "query_text": row.get("query_text") or "",
            "results": row.get("results") or [],
            "error": row.get("error") or "",
        }

    miss = [brief(r) for r in rows if not r.get("hit")]
    not_first = [brief(r) for r in rows if r.get("hit") and not r.get("first")]
    not_original = [brief(r) for r in rows if r.get("hit") and not r.get("gold_original")]
    extra = [brief(r) for r in rows if r.get("extra_originals", 0) > 0]
    return {
        "miss": miss[:limit],
        "not_first": not_first[:limit],
        "hit_not_marked_original": not_original[:limit],
        "extra_original": extra[:limit],
        "miss_count": len(miss),
        "not_first_count": len(not_first),
        "hit_not_marked_original_count": len(not_original),
        "extra_original_count": len(extra),
    }


def _pct(rate: float) -> str:
    return f"{100.0 * rate:.1f}%"


def _md_table(title: str, stats: dict[str, dict]) -> str:
    lines = [
        f"### {title}",
        "",
        "| 分组 | 样本 | 命中@3 | 首位 | 标成原题 | 误标其他原题 | 空结果 | 均返回 | 均耗时s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, row in stats.items():
        lines.append(
            f"| {name} | {row['samples']} | {_pct(row['hit_rate'])} | {_pct(row['first_rate'])} | "
            f"{_pct(row['gold_original_rate'])} | {_pct(row['extra_original_rate'])} | "
            f"{_pct(row['empty_rate'])} | {row['avg_returned']:.2f} | {row['avg_elapsed_s']:.2f} |"
        )
    lines.append("")
    return "\n".join(lines)


def _md_failures(title: str, payload: dict) -> str:
    lines = [f"### {title}", ""]
    lines.append(
        f"未命中 {payload['miss_count']}，命中但非首位 {payload['not_first_count']}，"
        f"命中但未标原题 {payload['hit_not_marked_original_count']}，"
        f"另标其他原题 {payload['extra_original_count']}。"
    )
    lines.append("")
    for label, key in (
        ("未命中", "miss"),
        ("命中但未标原题", "hit_not_marked_original"),
        ("另标其他原题", "extra_original"),
    ):
        items = payload.get(key) or []
        if not items:
            continue
        lines.append(f"**{label}（最多 15 条）**")
        lines.append("")
        for item in items[:15]:
            top = ", ".join(
                f"{c['id']}:{c['relation']}/{c['final']:.3f}" for c in (item.get("results") or [])[:3]
            ) or "（空）"
            q = (item.get("query_text") or "").replace("\n", " ")[:120]
            err = item.get("error") or ""
            extra = f" err={err}" if err else ""
            lines.append(f"- `{item['id']}` ({item.get('source')}) {q}{extra}")
            lines.append(f"  - top3: {top}")
        lines.append("")
    return "\n".join(lines)


def _empty_failures() -> dict:
    return {
        "miss": [],
        "not_first": [],
        "hit_not_marked_original": [],
        "extra_original": [],
        "miss_count": 0,
        "not_first_count": 0,
        "hit_not_marked_original_count": 0,
        "extra_original_count": 0,
    }


def load_text_section(
    text_rows: list[dict],
    tasks: list[dict],
    source_names: tuple[str, ...],
    math_ocr: bool = True,
) -> dict:
    if tasks and len(text_rows) >= len(tasks):
        return {
            "overall": summarize(text_rows),
            "by_source": by_key(text_rows, "source"),
            "by_kind": by_key(text_rows, "kind"),
            "failures": failure_samples(text_rows),
            "complete": True,
            "reused": False,
            "math_ocr": bool(math_ocr),
        }
    if TEXT_GOLD_LAST.is_file() and math_ocr:
        snap = json.loads(TEXT_GOLD_LAST.read_text(encoding="utf-8"))
        by_source = {
            name: snap["by_source"][name]
            for name in source_names
            if name in (snap.get("by_source") or {})
        }
        if len(source_names) == 3 and set(source_names) == {"ape", "cm17k", "geometry3k"}:
            overall = snap["overall"]
        else:
            overall = summarize([])
        return {
            "overall": overall,
            "by_source": by_source,
            "by_kind": {},
            "failures": _empty_failures(),
            "complete": True,
            "reused": True,
            "math_ocr": True,
            "note": snap.get("note") or "沿用上次文本金标汇总。",
        }
    return {
        "overall": summarize(text_rows),
        "by_source": by_key(text_rows, "source"),
        "by_kind": by_key(text_rows, "kind"),
        "failures": failure_samples(text_rows),
        "complete": False,
        "reused": False,
        "math_ocr": bool(math_ocr),
    }


def combine_stats(by_source: dict[str, dict]) -> dict:
    parts = [row for row in by_source.values() if int(row.get("samples") or 0) > 0]
    n = sum(int(row["samples"]) for row in parts)
    if not n:
        return summarize([])
    hit = sum(int(row.get("hit") or 0) for row in parts)
    first = sum(int(row.get("first") or 0) for row in parts)
    gold = sum(int(row.get("gold_original") or 0) for row in parts)
    extra = sum(int(row.get("extra_original") or 0) for row in parts)
    empty = sum(int(row.get("empty") or 0) for row in parts)
    return {
        "samples": n,
        "hit": hit,
        "first": first,
        "gold_original": gold,
        "extra_original": extra,
        "empty": empty,
        "hit_rate": hit / n,
        "first_rate": first / n,
        "gold_original_rate": gold / n,
        "extra_original_rate": extra / n,
        "empty_rate": empty / n,
        "avg_returned": sum(float(row.get("avg_returned") or 0) * int(row["samples"]) for row in parts) / n,
        "avg_elapsed_s": sum(float(row.get("avg_elapsed_s") or 0) * int(row["samples"]) for row in parts) / n,
    }


def _load_existing_report() -> dict | None:
    path = SET_DIR / "report.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _ordered_by_source(by_source: dict[str, dict]) -> dict[str, dict]:
    ordered: dict[str, dict] = {}
    for name in SOURCES:
        if name in by_source:
            ordered[name] = by_source[name]
    for name, row in by_source.items():
        if name not in ordered:
            ordered[name] = row
    return ordered


def write_report(
    text_rows: list[dict],
    image_rows: list[dict],
    tasks: list[dict],
    math_ocr: bool = True,
    sources: tuple[str, ...] | None = None,
) -> dict:
    source_names = tuple(sources) if sources else tuple(name for name in SOURCES if any(t.get("source") == name for t in tasks))
    source_counts = {name: sum(1 for t in tasks if t.get("source") == name) for name in source_names}
    source_label = " / ".join(f"{name} {source_counts[name]}" for name in source_names)
    text_section = load_text_section(text_rows, tasks, source_names, math_ocr=math_ocr)
    run_image = {
        "overall": summarize(image_rows),
        "by_source": by_key(image_rows, "source"),
        "by_kind": by_key(image_rows, "kind"),
        "failures": failure_samples(image_rows),
        "complete": bool(tasks) and len(image_rows) >= len(tasks),
        "coverage": len(image_rows) / len(tasks) if tasks else 0.0,
        "math_ocr": bool(math_ocr),
    }
    image_formula = (
        "图搜公式检测：**开**（题干 ∧ 公式 ∧ 附图）"
        if math_ocr
        else "图搜公式检测：**关**（题干 ∧ 附图；RapidOCR，不跑读题模型）"
    )
    text_formula = (
        "文本金标沿用上次（公式检测开）"
        if text_section.get("reused")
        else ("文本金标公式检测：**开**" if math_ocr else "文本金标公式检测：**关**")
    )
    image_heading = "渲染图（公式检测 + 读题模型）" if math_ocr else "渲染图（公式检测关：题干 ∧ 附图）"
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    existing = _load_existing_report()
    keep_others = bool(
        existing
        and existing.get("text", {}).get("by_source")
        and any(name not in source_names for name in (existing.get("sources") or existing["text"]["by_source"]))
    )
    if keep_others:
        text_by = dict(existing.get("text", {}).get("by_source") or {})
        image_by = dict(existing.get("image", {}).get("by_source") or {})
        flags = dict(existing.get("source_math_ocr") or {name: True for name in SOURCES})
        if text_section.get("complete"):
            for name in source_names:
                row = (text_section.get("by_source") or {}).get(name)
                if row:
                    text_by[name] = row
                    flags[name] = bool(math_ocr)
        if run_image["complete"]:
            for name in source_names:
                row = (run_image.get("by_source") or {}).get(name)
                if row:
                    image_by[name] = row
                    flags[name] = bool(math_ocr)
        text_by = _ordered_by_source(text_by)
        image_by = _ordered_by_source(image_by)
        off_sources = [name for name, flag in flags.items() if name in text_by and not flag]
        on_sources = [name for name, flag in flags.items() if name in text_by and flag]
        cfg = SearchConfig()
        report = {
            "name": "formula_10k",
            "generated_at": generated,
            "index": str(INDEX),
            "samples_total": sum(int(row.get("samples") or 0) for row in text_by.values()),
            "sources": list(text_by),
            "math_ocr": None,
            "source_math_ocr": flags,
            "note": "分数据源评测；公式检测开关见 source_math_ocr。",
            "thresholds": {
                "t_same": cfg.t_same,
                "t_ocr_same": cfg.t_ocr_same,
                "t_formula": cfg.t_formula,
                "t_diagram": cfg.t_diagram,
                "t_var": cfg.t_var,
                "recall_k": cfg.recall_k,
                "max_results": cfg.max_results,
            },
            "text": {
                "overall": combine_stats(text_by),
                "by_source": text_by,
                "by_kind": existing.get("text", {}).get("by_kind") or {},
                "failures": text_section["failures"] if text_section.get("complete") else existing.get("text", {}).get("failures") or _empty_failures(),
                "complete": True,
            },
            "image": {
                "overall": combine_stats(image_by),
                "by_source": image_by,
                "by_kind": run_image["by_kind"] if run_image["complete"] else existing.get("image", {}).get("by_kind") or {},
                "failures": run_image["failures"] if run_image["complete"] else existing.get("image", {}).get("failures") or _empty_failures(),
                "complete": True,
                "coverage": 1.0,
            },
        }
        flag_line = (
            f"- 公式检测关：{', '.join(off_sources) or '无'}；"
            f"公式检测开：{', '.join(on_sources) or '无'}"
        )
        combined_text_intro = "各数据源文本金标；本轮重跑的数据源已替换。"
        combined_image_heading = "渲染图"
        if run_image["complete"]:
            combined_status = "已完成（分数据源合并；未重跑的数据源保持上一轮）。"
        elif image_rows:
            combined_status = f"{', '.join(source_names)} 图搜进行中 {len(image_rows)}/{len(tasks)}。总表图搜在完成前仍显示上一轮。"
        else:
            combined_status = "已完成（分数据源合并；未重跑的数据源保持上一轮）。"
    else:
        cfg = SearchConfig()
        report = {
            "name": "formula_10k",
            "generated_at": generated,
            "index": str(INDEX),
            "samples_total": len(tasks),
            "sources": list(source_names),
            "math_ocr": bool(math_ocr),
            "source_math_ocr": {name: bool(math_ocr) for name in source_names},
            "note": "渲染白底题图，不是真实拍照；文本金标是识图上限。",
            "thresholds": {
                "t_same": cfg.t_same,
                "t_ocr_same": cfg.t_ocr_same,
                "t_formula": cfg.t_formula,
                "t_diagram": cfg.t_diagram,
                "t_var": cfg.t_var,
                "recall_k": cfg.recall_k,
                "max_results": cfg.max_results,
            },
            "text": text_section,
            "image": run_image,
        }
        flag_line = f"- {text_formula}"
        combined_text_intro = (
            "沿用上一轮公式检测开的文本金标汇总（不重跑）。"
            if text_section.get("reused")
            else "用各数据集目录下 `manifest.jsonl` 里的原题干直接检索，不经过 OCR/VLM。这是图搜上限。"
        )
        combined_image_heading = image_heading
        img = report["image"]["overall"]
        if img["samples"] == 0:
            combined_status = ""
        else:
            combined_status = "已完成" if report["image"]["complete"] else f"进行中 {img['samples']}/{len(tasks)}"
    query_label = (
        " / ".join(f"{name} {row['samples']}" for name, row in (report["text"].get("by_source") or {}).items())
        if keep_others
        else source_label
    )
    (SET_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# formula_10k 评测报告",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- 索引：`{INDEX}`",
        f"- 查询集：{report['samples_total']}（{query_label}）",
        flag_line,
        f"- {image_formula}",
        "- 图搜输入：渲染白底题图（Geometry3K 拼了原始配图）",
        "",
        "## 文本金标",
        "",
        combined_text_intro,
        "",
        _md_table("总体 / 按来源", {"all": report["text"]["overall"], **report["text"]["by_source"]}),
    ]
    if report["text"].get("by_kind"):
        lines.append(_md_table("按题型", report["text"]["by_kind"]))
    if not text_section.get("reused"):
        fail_title = "文本失败样例（本轮重跑数据源）" if keep_others else "文本失败样例"
        lines.append(_md_failures(fail_title, report["text"]["failures"]))
    lines.extend(
        [
            f"## {combined_image_heading}",
            "",
        ]
    )
    img = report["image"]["overall"]
    if img["samples"] == 0:
        lines.append("尚未开始图搜。")
        lines.append("")
    else:
        lines.append(f"状态：**{combined_status}**。")
        lines.append("")
        lines.append(_md_table("总体 / 按来源", {"all": img, **report["image"]["by_source"]}))
        if report["image"].get("by_kind"):
            lines.append(_md_table("按题型", report["image"]["by_kind"]))
        fail_title = "图搜失败样例（本轮重跑数据源）" if keep_others else "图搜失败样例"
        lines.append(_md_failures(fail_title, report["image"]["failures"]))
    (SET_DIR / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    for source in source_names:
        src_tasks = [t for t in tasks if t.get("source") == source]
        if not src_tasks:
            continue
        src_text = [r for r in text_rows if r.get("source") == source]
        src_image = [r for r in image_rows if r.get("source") == source]
        if text_section.get("reused") and source in (text_section.get("by_source") or {}):
            src_text_block = {
                "overall": text_section["by_source"][source],
                "by_kind": {},
                "failures": _empty_failures(),
                "complete": True,
                "reused": True,
            }
        else:
            src_text_block = {
                "overall": summarize(src_text),
                "by_kind": by_key(src_text, "kind"),
                "failures": failure_samples(src_text),
                "complete": len(src_text) >= len(src_tasks),
            }
        src_report = {
            "name": f"formula_10k/{source}",
            "source": source,
            "generated_at": report["generated_at"],
            "samples_total": len(src_tasks),
            "math_ocr": bool(math_ocr),
            "text": src_text_block,
            "image": {
                "overall": summarize(src_image),
                "by_kind": by_key(src_image, "kind"),
                "failures": failure_samples(src_image),
                "complete": len(src_image) >= len(src_tasks),
            },
        }
        root = source_root(source)
        root.mkdir(parents=True, exist_ok=True)
        (root / "report.json").write_text(json.dumps(src_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        src_lines = [
            f"# formula_10k / {source}",
            "",
            f"- 样本：{len(src_tasks)}",
            f"- {text_formula}",
            f"- {image_formula}",
            "",
            _md_table("文本金标", {"all": src_report["text"]["overall"], **(src_report["text"].get("by_kind") or {})}),
        ]
        if not src_report["text"].get("reused"):
            src_lines.append(_md_failures("文本失败样例", src_report["text"]["failures"]))
        src_img = src_report["image"]["overall"]
        if src_img["samples"] == 0:
            src_lines.append("尚未开始图搜。")
            src_lines.append("")
        else:
            src_lines.append(_md_table("渲染图", {"all": src_img, **src_report["image"]["by_kind"]}))
            src_lines.append(_md_failures("图搜失败样例", src_report["image"]["failures"]))
        (root / "report.md").write_text("\n".join(src_lines).rstrip() + "\n", encoding="utf-8")
    return report


def _pending(tasks: list[dict], done_ids: set[str]) -> list[dict]:
    return [task for task in tasks if task["id"] not in done_ids]


def _log_progress(phase: str, done: int, total: int, started: float, session_base: int) -> None:
    elapsed = max(time.time() - started, 1e-6)
    session = max(done - session_base, 1)
    rate = session / elapsed
    remain = (total - done) / rate if rate else 0.0
    print(
        f"{phase} {done}/{total} {rate:.2f}/s eta={remain / 60:.1f}min",
        flush=True,
    )


def _refresh_report(sources: tuple[str, ...], math_ocr: bool) -> None:
    write_report(
        load_results("text", sources),
        load_results("image", sources),
        load_tasks(sources),
        math_ocr=math_ocr,
        sources=sources,
    )


def run_text(
    gallery: Gallery,
    tasks: list[dict],
    resume: bool,
    sources: tuple[str, ...],
    math_ocr: bool,
) -> list[dict]:
    if not resume:
        clear_results("text", sources)
        existing = []
    else:
        existing = load_results("text", sources)
    done = {row["id"] for row in existing}
    pending = _pending(tasks, done)
    print(f"text math_ocr={math_ocr} resume={len(existing)} pending={len(pending)}", flush=True)
    started = time.time()
    session_base = len(existing)
    finished = session_base
    total = len(tasks)
    for i, task in enumerate(pending, 1):
        t0 = time.time()
        try:
            resp = search(gallery, text=task["original_text"], math_ocr=math_ocr)
            row = scored_row(task, "text", resp, time.time() - t0, math_ocr)
        except Exception as exc:
            row = empty_row(task, "text", str(exc), time.time() - t0, math_ocr)
        _append_jsonl(results_path(task["source"], "text"), row)
        existing.append(row)
        finished += 1
        if i % 200 == 0 or i == len(pending):
            _log_progress("text", finished, total, started, session_base)
            _refresh_report(sources, math_ocr)
    print("text_done", flush=True)
    return existing


def run_image(
    gallery: Gallery,
    tasks: list[dict],
    resume: bool,
    sources: tuple[str, ...],
    math_ocr: bool,
) -> list[dict]:
    if not resume:
        clear_results("image", sources)
        existing = []
    else:
        existing = load_results("image", sources)
    done = {row["id"] for row in existing}
    pending = _pending(tasks, done)
    print(f"image warmup math_ocr={math_ocr} pending={len(pending)} resume={len(existing)}", flush=True)
    ocr = get_ocr_backend("auto")
    if math_ocr:
        from eqsearch.vision.read_question import warmup_vision_reader

        warmup_vision_reader()
    print("image_warmup_done", flush=True)
    started = time.time()
    session_base = len(existing)
    finished = session_base
    total = len(tasks)
    for i, task in enumerate(pending, 1):
        t0 = time.time()
        png = Path(task["image"])
        if not png.is_file():
            row = empty_row(task, "image", f"missing image: {png}", time.time() - t0, math_ocr)
        else:
            try:
                resp = search(gallery, image=open_image(png), ocr=ocr, math_ocr=math_ocr)
                row = scored_row(task, "image", resp, time.time() - t0, math_ocr)
            except Exception as exc:
                row = empty_row(task, "image", str(exc), time.time() - t0, math_ocr)
        _append_jsonl(results_path(task["source"], "image"), row)
        existing.append(row)
        finished += 1
        if i % 20 == 0 or i == len(pending):
            _log_progress("image", finished, total, started, session_base)
            _refresh_report(sources, math_ocr)
    print("image_done", flush=True)
    return existing


def main() -> None:
    parser = argparse.ArgumentParser(description="formula_10k 评测并写 report.md")
    parser.add_argument("--phase", choices=["text", "image", "both"], default="both")
    parser.add_argument("--sources", default="all", help="逗号分隔：ape,cm17k,math,geometry3k 或 all")
    parser.add_argument(
        "--math-ocr",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="公式检测：开则题干∧公式∧附图；--no-math-ocr 只比题干和附图",
    )
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    sources = parse_sources(args.sources)
    math_ocr = bool(args.math_ocr)
    tasks = load_tasks(sources)
    if not tasks:
        raise SystemExit(f"缺少测试集：{[str(source_root(s) / 'manifest.jsonl') for s in sources]}")
    print(f"load index {INDEX} tasks={len(tasks)} sources={list(sources)} math_ocr={math_ocr}", flush=True)
    gallery = Gallery.load(INDEX, SearchConfig())
    print(f"gallery={len(gallery.items)}", flush=True)
    if args.phase in {"text", "both"}:
        run_text(gallery, tasks, resume=args.resume, sources=sources, math_ocr=math_ocr)
    if args.phase in {"image", "both"}:
        run_image(gallery, tasks, resume=args.resume, sources=sources, math_ocr=math_ocr)
    report = write_report(
        load_results("text", sources),
        load_results("image", sources),
        tasks,
        math_ocr=math_ocr,
        sources=sources,
    )
    print(json.dumps({"math_ocr": math_ocr, "text": report["text"]["overall"], "image": report["image"]["overall"]}, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
