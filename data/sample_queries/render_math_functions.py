"""Render MATH function-problem worksheets for image-search tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
MATH = ROOT / "data" / "raw" / "math"
OUT = Path(__file__).resolve().parent / "math"
FONT_PATH = Path(r"C:\Windows\Fonts\arial.ttf")

# (jsonl stem, line index, output stem, optional OCR-friendly wording)
PICKS = [
    ("algebra_train", 0, "math_train_algebra_0_piecewise_continuous", None),
    ("algebra_test", 157, "math_test_algebra_157_compose_equal", None),
    (
        "algebra_test",
        180,
        "math_test_algebra_180_nested_inverses",
        "Let f(x)=x+1 and g(x)=2x. Also denote the inverses to these functions as f^-1 and g^-1. Compute f(g^-1(f^-1(f^-1(g(f(5)))))).",
    ),
    ("algebra_test", 184, "math_test_algebra_184_piecewise_inverse", None),
    (
        "algebra_train",
        1478,
        "math_train_algebra_1478_nested_h",
        "Let f(x) = 2x + 5\ng(x) = sqrt(f(x)) - 2\nh(x) = f(g(x))\nWhat is h(2)?",
    ),
    ("algebra_test", 1049, "math_test_algebra_1049_alternating_fg", None),
    (
        "precalculus_test",
        412,
        "math_test_precalculus_412_log_sqrt_sin",
        "What is the range of the function y = log_2 ( sqrt(sin x) ) for 0 degrees < x < 180 degrees?",
    ),
    ("intermediate_algebra_test", 124, "math_test_intermediate_algebra_124_odd_even", None),
]


def latex_to_plain(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\\begin\{cases\}", "\n", text)
    text = re.sub(r"\\end\{cases\}", "\n", text)
    text = re.sub(r"\\begin\{array\}(?:\{[^}]*\})?", "\n", text)
    text = re.sub(r"\\end\{array\}", "\n", text)
    text = re.sub(r"\\begin\{align\*?\}", "\n", text)
    text = re.sub(r"\\end\{align\*?\}", "\n", text)
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


def wrap_line(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def render_worksheet(problem: str, dest: Path) -> None:
    font = ImageFont.truetype(str(FONT_PATH), 24)
    plain = latex_to_plain(problem)
    probe = Image.new("RGB", (10, 10), "white")
    draw = ImageDraw.Draw(probe)
    max_width = 820
    lines: list[str] = []
    for para in plain.split("\n"):
        lines.extend(wrap_line(draw, para, font, max_width))
        lines.append("")
    while lines and not lines[-1]:
        lines.pop()
    line_h = 40
    width = 920
    height = 56 + line_h * len(lines) + 40
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    y = 28
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += line_h
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)


def load_record(stem: str, index: int) -> dict:
    path = MATH / f"{stem}.jsonl"
    for i, line in enumerate(path.open(encoding="utf-8")):
        if i == index:
            return json.loads(line)
    raise KeyError(f"{stem} line {index}")


def item_id(stem: str, index: int) -> str:
    split = "train" if stem.endswith("_train") else "test"
    subject = stem[: -len("_train")] if stem.endswith("_train") else stem[: -len("_test")]
    return f"math-{split}-{subject.replace('_', '-')}-{index}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for stem, index, name, override in PICKS:
        rec = load_record(stem, index)
        dest = OUT / f"{name}.png"
        render_worksheet(override or rec["problem"], dest)
        iid = item_id(stem, index)
        rows.append(f"{dest.name}\t{iid}\t{rec.get('level')}\t{rec.get('type')}")
        print("wrote", dest.name, "->", iid)
    (OUT / "manifest.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
