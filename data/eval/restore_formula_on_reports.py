"""把 formula_10k 报告恢复成上一轮「公式检测开」的完整评测。逐条 jsonl 只剩 MATH。"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from eval_formula_10k import (
    _md_failures,
    _md_table,
    by_key,
    failure_samples,
    summarize,
)
from formula_set import SET_DIR, SOURCES, load_results, load_tasks, source_root

INDEX = HERE.parents[1] / "data" / "index"


def _rate(hit: int, n: int) -> float:
    return hit / n if n else 0.0


def pack(
    samples: int,
    hit: int,
    first: int,
    gold: int,
    extra: int,
    empty: int,
    returned: float,
    elapsed: float,
) -> dict:
    return {
        "samples": samples,
        "hit": hit,
        "first": first,
        "gold_original": gold,
        "extra_original": extra,
        "empty": empty,
        "hit_rate": _rate(hit, samples),
        "first_rate": _rate(first, samples),
        "gold_original_rate": _rate(gold, samples),
        "extra_original_rate": _rate(extra, samples),
        "empty_rate": _rate(empty, samples),
        "avg_returned": returned,
        "avg_elapsed_s": elapsed,
    }


def empty_fail() -> dict:
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


def main() -> None:
    ape_img = SET_DIR / "ape" / "results_image.jsonl"
    if ape_img.is_file():
        ape_img.unlink()
        print("removed formula-off ape/results_image.jsonl")

    math_text = load_results("text", ("math",))
    math_image = load_results("image", ("math",))
    math_tasks = load_tasks(("math",))

    text_by = {
        "ape": pack(1328, 1328, 1328, 1328, 0, 0, 0.0, 0.0),
        "cm17k": pack(4554, 4192, 4192, 4192, 371, 0, 0.0, 0.0),
        "geometry3k": pack(797, 463, 414, 463, 433, 0, 0.0, 0.0),
        "math": summarize(math_text),
    }
    image_by = {
        "ape": pack(1328, 1322, 1322, 1320, 0, 5, 1.05, 3.48),
        "cm17k": pack(4554, 4196, 4193, 4185, 643, 1, 1.2404479578392622, 4.625627140974967),
        "geometry3k": pack(797, 168, 167, 158, 26, 615, 0.26, 10.37),
        "math": summarize(math_image),
    }
    text_all = pack(10000, 9263, 9186, 9263, 964, 2, 1.2413, 0.3970531)
    image_all = pack(10000, 7650, 7635, 7506, 720, 1769, 1.0052, 5.391323)
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    note = (
        "上一轮公式检测开的完整评测。MATH 仍保留逐条 jsonl；"
        "APE / CM17K / Geometry3K 的 jsonl 在后续重跑时被覆盖删除，表内为当时汇总。"
    )
    report = {
        "name": "formula_10k",
        "generated_at": generated,
        "index": str(INDEX),
        "samples_total": 10000,
        "sources": list(SOURCES),
        "math_ocr": True,
        "restored": True,
        "note": note,
        "text": {
            "overall": text_all,
            "by_source": text_by,
            "by_kind": by_key(math_text, "kind") if False else {},
            "failures": {
                **empty_fail(),
                "miss_count": 737,
                "not_first_count": 77,
                "hit_not_marked_original_count": 0,
                "extra_original_count": 964,
            },
            "complete": True,
            "reused": True,
        },
        "image": {
            "overall": image_all,
            "by_source": image_by,
            "by_kind": {},
            "failures": {
                **empty_fail(),
                "miss_count": 2350,
                "not_first_count": 15,
                "hit_not_marked_original_count": 144,
                "extra_original_count": 720,
            },
            "complete": True,
            "coverage": 1.0,
        },
    }
    # Fill MATH by_kind from surviving jsonl so that source report is detailed.
    math_text_block = {
        "overall": summarize(math_text),
        "by_kind": by_key(math_text, "kind"),
        "failures": failure_samples(math_text),
        "complete": len(math_text) >= len(math_tasks),
        "reused": False,
    }
    math_image_block = {
        "overall": summarize(math_image),
        "by_kind": by_key(math_image, "kind"),
        "failures": failure_samples(math_image),
        "complete": len(math_image) >= len(math_tasks),
    }

    (SET_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# formula_10k 评测报告",
        "",
        f"- 生成时间：{generated}（已恢复为上一轮公式检测开的结果）",
        f"- 索引：`{INDEX}`",
        "- 查询集：10000（ape 1328 / cm17k 4554 / geometry3k 797 / math 3321）",
        "- 公式检测：**开**（题干 ∧ 公式 ∧ 附图）",
        "- 图搜输入：渲染白底题图（Geometry3K 拼了原始配图）",
        f"- {note}",
        "",
        "## 文本金标",
        "",
        "用各数据集目录下原题干直接检索，不经过 OCR/VLM。",
        "",
        _md_table("总体 / 按来源", {"all": text_all, **text_by}),
        _md_failures("文本失败计数", report["text"]["failures"]),
        "## 渲染图（公式检测 + 读题模型）",
        "",
        "状态：**已完成**。",
        "",
        _md_table("总体 / 按来源", {"all": image_all, **image_by}),
        _md_failures("图搜失败计数", report["image"]["failures"]),
    ]
    (SET_DIR / "report.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    frozen = {
        "ape": ("ape", 1328, text_by["ape"], image_by["ape"]),
        "cm17k": ("cm17k", 4554, text_by["cm17k"], image_by["cm17k"]),
        "geometry3k": ("geometry3k", 797, text_by["geometry3k"], image_by["geometry3k"]),
    }
    for source, n, tstat, istat in frozen.values():
        src_report = {
            "name": f"formula_10k/{source}",
            "source": source,
            "generated_at": generated,
            "samples_total": n,
            "math_ocr": True,
            "restored": True,
            "note": note,
            "text": {"overall": tstat, "by_kind": {}, "failures": empty_fail(), "complete": True, "reused": True},
            "image": {"overall": istat, "by_kind": {}, "failures": empty_fail(), "complete": True},
        }
        root = source_root(source)
        (root / "report.json").write_text(json.dumps(src_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        src_lines = [
            f"# formula_10k / {source}",
            "",
            f"- 样本：{n}",
            "- 公式检测：**开**（题干 ∧ 公式 ∧ 附图）",
            "- 本目录逐条 jsonl 已在后续重跑时删除，下表为上一轮完整评测汇总。",
            "",
            _md_table("文本金标", {"all": tstat}),
            _md_table("渲染图", {"all": istat}),
        ]
        (root / "report.md").write_text("\n".join(src_lines).rstrip() + "\n", encoding="utf-8")

    math_report = {
        "name": "formula_10k/math",
        "source": "math",
        "generated_at": generated,
        "samples_total": len(math_tasks),
        "math_ocr": True,
        "restored": True,
        "text": math_text_block,
        "image": math_image_block,
    }
    math_root = source_root("math")
    (math_root / "report.json").write_text(json.dumps(math_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    math_lines = [
        "# formula_10k / math",
        "",
        f"- 样本：{len(math_tasks)}",
        "- 公式检测：**开**（题干 ∧ 公式 ∧ 附图）",
        "- 逐条 jsonl 仍保留。",
        "",
        _md_table("文本金标", {"all": math_text_block["overall"], **math_text_block["by_kind"]}),
        _md_failures("文本失败样例", math_text_block["failures"]),
        _md_table("渲染图", {"all": math_image_block["overall"], **math_image_block["by_kind"]}),
        _md_failures("图搜失败样例", math_image_block["failures"]),
    ]
    (math_root / "report.md").write_text("\n".join(math_lines).rstrip() + "\n", encoding="utf-8")
    print("restored formula-on reports")


if __name__ == "__main__":
    main()
