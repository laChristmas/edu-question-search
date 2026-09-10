"""附图：紧裁墨迹、16×16 布局向量。不用整张照片的颜色直方图。"""

from __future__ import annotations

import numpy as np
from PIL import Image


def canonicalize_figure(image: Image.Image, size: int = 128) -> Image.Image:
    """Tight-crop ink and pad to a square so photo scale/position do not dominate."""
    rgb = image.convert("RGB")
    gray = np.asarray(rgb.convert("L"))
    ink = gray < 180
    ys, xs = np.where(ink)
    if len(xs) < 8:
        return rgb.resize((size, size), Image.Resampling.BILINEAR)
    pad = 2
    h, w = gray.shape
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(w, int(xs.max()) + 1 + pad), min(h, int(ys.max()) + 1 + pad)
    cropped = rgb.crop((x0, y0, x1, y1))
    cw, ch = cropped.size
    side = max(cw, ch, 1)
    canvas = Image.new("RGB", (side, side), "white")
    canvas.paste(cropped, ((side - cw) // 2, (side - ch) // 2))
    return canvas.resize((size, size), Image.Resampling.BILINEAR)


def ink_vector(image: Image.Image, size: int = 16) -> list[float]:
    """Spatial ink grid of a cropped figure. Background clutter must be cropped away first."""
    canon = canonicalize_figure(image)
    gray = np.asarray(canon.convert("L"))
    ink = (gray < 180).astype(np.uint8) * 255
    try:
        import cv2

        ink = cv2.dilate(ink, np.ones((3, 3), np.uint8), iterations=2)
    except ImportError:
        pass
    small = np.asarray(Image.fromarray(ink).resize((size, size), Image.Resampling.BILINEAR), dtype=np.float32)
    vec = (small > 40).astype(np.float32).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec = vec / norm
    return vec.tolist()


def histogram_vector(image: Image.Image, bins: int = 16) -> list[float]:
    """Deprecated color histogram; kept as an alias to ink_vector for older imports."""
    return ink_vector(image)


def mean_diagram_vector(crops: list[Image.Image]) -> list[float] | None:
    if not crops:
        return None
    stacked = np.stack([np.asarray(ink_vector(c), dtype=np.float32) for c in crops])
    mean = stacked.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm > 0:
        mean = mean / norm
    return mean.tolist()


def diagram_similarity(a: list[float] | None, b: list[float] | None) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    left = np.asarray(a, dtype=np.float32)
    right = np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denom <= 1e-8:
        return 0.0
    return float(np.dot(left, right) / denom)
