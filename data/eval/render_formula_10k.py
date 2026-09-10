"""把 formula_10k 题干渲染成白底题目图；MATH / Geometry3K 编译 LaTeX，有配图则拼在题干下方。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from formula_set import image_dir, image_path, load_manifests, parse_sources, safe_name

ROOT = HERE.parents[1]
CJK_FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
LATIN_FONT = Path(r"C:\Windows\Fonts\arial.ttf")
MAX_WIDTH = 820
PAGE_W = 920
MAX_LINES = 56
LINE_H = 36
LATEX_SOURCES = {"math", "geometry3k"}


def latex_to_plain(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\\begin\{cases\}", "\n", text)
    text = re.sub(r"\\end\{cases\}", "\n", text)
    text = re.sub(r"\\begin\{array\}(?:\{[^}]*\})?", "\n", text)
    text = re.sub(r"\\end\{array\}", "\n", text)
    text = re.sub(r"\\begin\{align\*?\}", "\n", text)
    text = re.sub(r"\\end\{align\*?\}", "\n", text)
    text = re.sub(r"\\begin\{aligned\}", "\n", text)
    text = re.sub(r"\\end\{aligned\}", "\n", text)
    text = text.replace(r"\\", "\n")
    text = text.replace("&", " ")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    text = re.sub(r"\\mathrm\{([^}]*)\}", r"\1", text)
    for _ in range(4):
        text = re.sub(r"\\(?:d|t)?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1)/(\2)", text)
    text = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", text)
    text = text.replace(r"\left", "").replace(r"\right", "")
    text = text.replace(r"\[", " ").replace(r"\]", " ")
    text = text.replace(r"\leq", "<=").replace(r"\geq", ">=")
    text = text.replace(r"\le", "<=").replace(r"\ge", ">=").replace(r"\neq", "!=")
    text = text.replace(r"\times", " x ").replace(r"\cdot", "·")
    text = text.replace(r"\infty", "inf")
    text = text.replace(r"\cdots", "...").replace(r"\dotsb", "...").replace(r"\ldots", "...")
    text = text.replace(r"^\circ", " degrees")
    text = text.replace(r"\circ", " o ")
    text = re.sub(r"\\log_\{([^}]+)\}", r"log_\1", text)
    text = text.replace(r"\log", "log").replace(r"\ln", "ln")
    text = text.replace(r"\sin", "sin").replace(r"\cos", "cos").replace(r"\tan", "tan")
    text = re.sub(r"\^\{([^{}]+)\}", r"^\1", text)
    text = re.sub(r"_\{([^{}]+)\}", r"_\1", text)
    text = re.sub(r"\\[a-zA-Z]+\*?", " ", text)
    text = text.replace("$", "")
    text = text.replace("{", "").replace("}", "")
    text = text.replace("[", "").replace("]", "")
    text = text.replace("\\", " ")
    lines = [" ".join(part.split()) for part in text.split("\n")]
    return "\n".join(line for line in lines if line)


def load_font(size: int, cjk: bool) -> ImageFont.FreeTypeFont:
    path = CJK_FONT if cjk else LATIN_FONT
    try:
        return ImageFont.truetype(str(path), size, index=0)
    except OSError:
        return ImageFont.truetype(str(LATIN_FONT), size)


def needs_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    probe = Image.new("RGB", (10, 10), "white")
    draw = ImageDraw.Draw(probe)
    lines: list[str] = []
    for para in (text or "").split("\n"):
        if not para.strip():
            lines.append("")
            continue
        current = ""
        for ch in para:
            trial = current + ch
            if draw.textlength(trial, font=font) <= max_width:
                current = trial
                continue
            brk = max(current.rfind(" "), current.rfind("\u3000"))
            if brk > 0:
                lines.append(current[:brk].rstrip())
                current = (current[brk + 1 :] + ch).lstrip()
            else:
                if current:
                    lines.append(current)
                current = ch
        if current:
            lines.append(current)
    while lines and not lines[-1]:
        lines.pop()
    return lines or [""]


def render_text_block(text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    lines = wrap_text(text, font, MAX_WIDTH)
    if len(lines) > MAX_LINES:
        lines = lines[: MAX_LINES - 1] + ["..."]
    height = 48 + LINE_H * len(lines) + 28
    img = Image.new("RGB", (PAGE_W, height), "white")
    draw = ImageDraw.Draw(img)
    y = 24
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += LINE_H
    return img


def scale_figure(path: Path, max_w: int = 820, max_h: int = 520) -> Image.Image:
    fig = Image.open(path).convert("RGB")
    w, h = fig.size
    scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
    if scale < 1:
        fig = fig.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.BILINEAR)
    return fig


def compose(stem: Image.Image, figure: Image.Image | None) -> Image.Image:
    if figure is None:
        return stem
    gap = 16
    width = max(PAGE_W, stem.width, figure.width + 80)
    height = stem.height + figure.height + gap + 24
    canvas = Image.new("RGB", (width, height), "white")
    canvas.paste(stem, (0, 0))
    x = max(40, (width - figure.width) // 2)
    canvas.paste(figure, (x, stem.height + gap))
    return canvas


def display_text(row: dict) -> str:
    raw = str(row.get("original_text") or "").strip() or row["id"]
    if row.get("source") == "math" or (not needs_cjk(raw) and ("\\" in raw or "$" in raw)):
        return latex_to_plain(raw) or raw
    return raw


def render_plain(row: dict) -> Image.Image:
    text = display_text(row)
    font = load_font(22, needs_cjk(text) or row.get("source") in {"ape", "cm17k"})
    return render_text_block(text, font)


def render_stem(row: dict, use_latex: bool) -> Image.Image:
    raw = str(row.get("original_text") or "").strip() or row["id"]
    source = str(row.get("source") or "")
    if use_latex and source in LATEX_SOURCES:
        from latex_page import render_stem as latex_stem

        try:
            return latex_stem(raw, source)
        except Exception:
            from latex_page import strip_asy

            fallback = strip_asy(raw)
            font = load_font(22, False)
            return render_text_block(latex_to_plain(fallback) or fallback, font)
    return render_plain(row)


def attached_figure(row: dict) -> Image.Image | None:
    image_path = row.get("image")
    if not image_path:
        return None
    path = Path(str(image_path))
    if not path.is_absolute():
        path = ROOT / path
    if path.is_file():
        return scale_figure(path)
    return None


def render_row(row: dict, use_latex: bool) -> Image.Image:
    return compose(render_stem(row, use_latex), attached_figure(row))


def _one(row: dict, dest: Path, use_latex: bool) -> tuple[str, str]:
    item_id = str(row["id"])
    try:
        render_row(row, use_latex).save(dest, format="PNG")
        return item_id, ""
    except Exception as exc:
        return item_id, str(exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="渲染 formula_10k 测试图")
    parser.add_argument("--sources", default="all", help="逗号分隔：ape,cm17k,math,geometry3k 或 all")
    parser.add_argument("--force", action="store_true", help="覆盖已有 PNG")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    wanted = parse_sources(args.sources)
    rows = load_manifests(wanted)
    if not rows:
        raise SystemExit(f"缺少测试集：{[str(image_dir(s).parent / 'manifest.jsonl') for s in wanted]}")
    if args.limit:
        rows = rows[: args.limit]
    for source in {str(row.get("source") or "") for row in rows}:
        image_dir(source).mkdir(parents=True, exist_ok=True)
    use_latex = any(str(row.get("source")) in LATEX_SOURCES for row in rows)
    if use_latex:
        from latex_page import ensure_tectonic, warmup

        ensure_tectonic()
        print("latex warmup...", flush=True)
        warmup()
        print("latex engine ready", flush=True)
    jobs: list[tuple[dict, Path]] = []
    skipped = 0
    for row in rows:
        dest = image_path(str(row.get("source") or "unknown"), str(row["id"]))
        if dest.is_file() and dest.stat().st_size > 0 and not args.force:
            skipped += 1
            continue
        jobs.append((row, dest))
    failed: list[str] = []
    ok = skipped
    workers = max(1, min(args.workers, len(jobs) or 1))
    print(f"render n={len(rows)} jobs={len(jobs)} skip={skipped} workers={workers}", flush=True)
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_one, row, dest, use_latex): (row, dest) for row, dest in jobs}
            done = 0
            for fut in as_completed(futs):
                item_id, err = fut.result()
                done += 1
                if err:
                    failed.append(f"{item_id}\t{err}")
                else:
                    ok += 1
                if done % 50 == 0 or done == len(jobs):
                    print(f"{done}/{len(jobs)} ok={ok} fail={len(failed)}", flush=True)
    by_src: dict[str, list[dict]] = {}
    for row in rows:
        by_src.setdefault(str(row.get("source") or "unknown"), []).append(row)
    fail_by_src: dict[str, list[str]] = {}
    for line in failed:
        item_id = line.split("\t", 1)[0]
        source = next((str(r.get("source")) for r in rows if str(r["id"]) == item_id), "unknown")
        fail_by_src.setdefault(source, []).append(line)
    for source, items in by_src.items():
        out = image_dir(source)
        mapping = [f"{safe_name(str(row['id']))}.png\t{row['id']}" for row in items]
        (out / "manifest.txt").write_text("\n".join(mapping) + "\n", encoding="utf-8")
        source_failed = fail_by_src.get(source) or []
        summary = {
            "images": len(items) - len(source_failed),
            "jobs": len(jobs),
            "skipped_existing": skipped,
            "failed": len(source_failed),
            "source": source,
            "force": bool(args.force),
            "dir": str(out),
        }
        (out / "render_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fail_path = out / "render_failed.txt"
        if source_failed:
            fail_path.write_text("\n".join(source_failed) + "\n", encoding="utf-8")
        elif fail_path.is_file():
            fail_path.unlink()
    summary = {
        "images": ok,
        "jobs": len(jobs),
        "skipped_existing": skipped,
        "failed": len(failed),
        "sources": list(wanted),
        "force": bool(args.force),
        "dirs": {source: str(image_dir(source)) for source in by_src},
    }
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
