"""把 MATH / Geometry3K 题干编成 LaTeX 再栅格化成白底 PNG。"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
TOOLS = HERE / ".tools"
TECTONIC_URL = (
    "https://github.com/tectonic-typesetting/tectonic/releases/download/"
    "tectonic%400.15.0/tectonic-0.15.0-x86_64-pc-windows-msvc.zip"
)
_ASY = re.compile(r"\[asy\].*?\[/asy\]", re.I | re.S)
_MACRO = re.compile(r"\\[a-zA-Z]+(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\})*")
_PREAMBLE = r"""
\documentclass[12pt]{article}
\usepackage[paperwidth=9.2in,paperheight=48in,margin=0.5in]{geometry}
\usepackage{amsmath,amssymb,amsfonts,mathtools}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.55em}
\raggedright
\begin{document}
"""


def strip_asy(text: str) -> str:
    text = _ASY.sub("\n", text or "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def escape_percents(text: str) -> str:
    return re.sub(r"(?<!\\)%", r"\\%", text)


def display_dollars_to_brackets(text: str) -> str:
    return re.sub(r"\$\$(.+?)\$\$", r"\\[\1\\]", text, flags=re.S)


def prepare_body(text: str, source: str) -> str:
    body = strip_asy(text or "")
    body = display_dollars_to_brackets(body)
    body = escape_percents(body)
    if source == "geometry3k":
        body = geometry_to_latex(body)
    return body


def geometry_to_latex(text: str) -> str:
    """Geometry3K 题干里的 \\angle / \\frac 多半不在数学模式，包进 $...$。"""
    if "$" in text or r"\[" in text:
        return text
    return _MACRO.sub(lambda m: f"${m.group(0)}$", text)


def tectonic_exe() -> Path:
    return TOOLS / "tectonic.exe"


def ensure_tectonic() -> Path:
    exe = tectonic_exe()
    if exe.is_file() and exe.stat().st_size > 1_000_000:
        return exe
    TOOLS.mkdir(parents=True, exist_ok=True)
    zip_path = TOOLS / "tectonic.zip"
    urllib.request.urlretrieve(TECTONIC_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(TOOLS)
    if not exe.is_file():
        raise FileNotFoundError(f"tectonic 解压后未找到 {exe}")
    return exe


def _crop_whitespace(img: Image.Image, pad: int = 28) -> Image.Image:
    arr = np.asarray(img.convert("RGB"))
    ink = (arr < 248).any(axis=2)
    if not ink.any():
        return img
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(cols[0]), int(cols[-1]) + 1
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(arr.shape[0], y1 + pad)
    x1 = min(arr.shape[1], x1 + pad)
    return img.crop((x0, y0, x1, y1))


def pdf_to_image(pdf_path: Path, dpi: int = 160) -> Image.Image:
    import pymupdf

    doc = pymupdf.open(pdf_path)
    try:
        page = doc[0]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    finally:
        doc.close()
    return _crop_whitespace(img)


def compile_latex(body: str, timeout: int = 90) -> Image.Image:
    exe = ensure_tectonic()
    tex = _PREAMBLE + body + "\n\\end{document}\n"
    with tempfile.TemporaryDirectory(prefix="texpage_", dir=str(TOOLS), ignore_cleanup_errors=True) as raw:
        work = Path(raw)
        tex_path = work / "q.tex"
        tex_path.write_text(tex, encoding="utf-8")
        env = os.environ.copy()
        env.setdefault("TECTONIC_CACHE_DIR", str(TOOLS / "cache"))
        proc = subprocess.run(
            [str(exe), "--chatter", "minimal", "-o", str(work), str(tex_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(work),
        )
        pdf = work / "q.pdf"
        if proc.returncode != 0 or not pdf.is_file():
            err = (proc.stderr or proc.stdout or "tectonic failed").strip()
            raise RuntimeError(err[-1500:] if err else "tectonic failed")
        return pdf_to_image(pdf)


def warmup() -> None:
    """第一次会拉 TeX 宏包，必须在并发渲染前单独跑完。"""
    compile_latex(r"Warmup $\dfrac{x-3}{2x^{2}-8x+7}$ and $\angle ABC$.", timeout=300)


def render_stem(text: str, source: str) -> Image.Image:
    return compile_latex(prepare_body(text, source))
