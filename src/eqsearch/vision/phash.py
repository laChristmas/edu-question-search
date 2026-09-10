from __future__ import annotations

from PIL import Image
import imagehash


def perceptual_hash(image: Image.Image) -> str:
    return str(imagehash.phash(image.convert("RGB")))


def hamming_distance(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        left = imagehash.hex_to_hash(a)
        right = imagehash.hex_to_hash(b)
    except (ValueError, TypeError):
        return None
    return int(left - right)
