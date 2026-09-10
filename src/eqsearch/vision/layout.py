"""Crop attached figures. Never treat the full phone photo as a diagram."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class OcrLine:
    text: str
    box: tuple[int, int, int, int]


def boxes_from_rapid(result: object) -> list[OcrLine]:
    txts = list(getattr(result, "txts", None) or [])
    boxes = getattr(result, "boxes", None)
    lines: list[OcrLine] = []
    if boxes is None:
        return [OcrLine(text=t, box=(0, 0, 0, 0)) for t in txts if t]
    for i, box in enumerate(np.asarray(boxes)):
        text = str(txts[i]) if i < len(txts) else ""
        if not text:
            continue
        pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
        x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
        x1, y1 = int(pts[:, 0].max()), int(pts[:, 1].max())
        lines.append(OcrLine(text=text, box=(x0, y0, x1, y1)))
    return lines


def reading_order_text(lines: list[OcrLine]) -> str:
    if not lines:
        return ""
    heights = [max(8, line.box[3] - line.box[1]) for line in lines if line.box[3] > line.box[1]]
    row = int(np.median(heights)) if heights else 16
    ordered = sorted(lines, key=lambda line: (line.box[1] // max(row, 1), line.box[0]))
    return "".join(line.text for line in ordered)


def stem_text(lines: list[OcrLine]) -> str:
    """Keep sentence-length OCR lines; drop diagram labels like O, B, CBD."""
    long_lines = [line for line in lines if len("".join(line.text.split())) >= 4]
    return reading_order_text(long_lines or lines)


def extract_diagram_crops(
    image: Image.Image,
    text_boxes: list[tuple[int, int, int, int]] | None = None,
    max_crops: int = 2,
) -> list[Image.Image]:
    """Keep large ink regions that are not OCR text. Drop page background and tiny clutter."""
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    h, w = arr.shape[:2]
    if h < 16 or w < 16:
        return []
    gray = np.asarray(rgb.convert("L"))
    ink = gray < 180
    text_mask = np.zeros((h, w), dtype=bool)
    pad = max(4, min(w, h) // 80)
    for box in text_boxes or []:
        x0, y0, x1, y1 = box
        text_mask[
            max(0, y0 - pad) : min(h, y1 + pad),
            max(0, x0 - pad) : min(w, x1 + pad),
        ] = True
    fig = ink & ~text_mask
    try:
        import cv2
    except ImportError:
        return _fallback_crop(rgb, fig)
    kernel = np.ones((5, 5), np.uint8)
    thick = cv2.dilate((fig.astype(np.uint8) * 255), kernel, iterations=3)
    num, _labels, stats, _ = cv2.connectedComponentsWithStats(thick, connectivity=8)
    min_box = max(24 * 24, int(0.008 * w * h))
    min_ink = 30
    boxes: list[tuple[int, int, int, int]] = []
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < min_ink or bw < 12 or bh < 12:
            continue
        if bw >= int(0.92 * w) and bh >= int(0.92 * h):
            continue
        box_area = int(bw) * int(bh)
        if box_area < min_box:
            continue
        boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
    merged = _merge_nearby_boxes(boxes, gap=max(28, min(w, h) // 18))
    merged = [
        b
        for b in merged
        if not ((b[2] - b[0]) >= int(0.92 * w) and (b[3] - b[1]) >= int(0.92 * h))
    ]
    candidates = [((b[2] - b[0]) * (b[3] - b[1]), b) for b in merged]
    candidates.sort(reverse=True)
    crops: list[Image.Image] = []
    used: list[tuple[int, int, int, int]] = []
    for _area, box in candidates:
        if any(_overlap(box, other) > 0.4 for other in used):
            continue
        crops.append(_padded_crop(rgb, box))
        used.append(box)
        if len(crops) >= max_crops:
            break
    return crops


def _fallback_crop(image: Image.Image, fig: np.ndarray) -> list[Image.Image]:
    ys, xs = np.where(fig)
    if len(xs) < 200:
        return []
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    w, h = image.size
    if (box[2] - box[0]) >= int(0.92 * w) and (box[3] - box[1]) >= int(0.92 * h):
        return []
    return [_padded_crop(image, box)]


def _merge_nearby_boxes(
    boxes: list[tuple[int, int, int, int]],
    gap: int,
) -> list[tuple[int, int, int, int]]:
    if not boxes:
        return []
    remaining = list(boxes)
    merged: list[tuple[int, int, int, int]] = []
    while remaining:
        x0, y0, x1, y1 = remaining.pop(0)
        changed = True
        while changed:
            changed = False
            nxt: list[tuple[int, int, int, int]] = []
            expand = (x0 - gap, y0 - gap, x1 + gap, y1 + gap)
            for other in remaining:
                if _overlap(expand, other) > 0:
                    x0 = min(x0, other[0])
                    y0 = min(y0, other[1])
                    x1 = max(x1, other[2])
                    y1 = max(y1, other[3])
                    changed = True
                else:
                    nxt.append(other)
            remaining = nxt
        merged.append((x0, y0, x1, y1))
    return merged


def _padded_crop(image: Image.Image, box: tuple[int, int, int, int], pad: int = 6) -> Image.Image:
    w, h = image.size
    x0, y0, x1, y1 = box
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(w, x1 + pad)
    y1 = min(h, y1 + pad)
    return image.crop((x0, y0, x1, y1))


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    inter = max(0, ix1 - ix0) * max(0, iy1 - iy0)
    area = max(1, (ax1 - ax0) * (ay1 - ay0))
    return inter / area
