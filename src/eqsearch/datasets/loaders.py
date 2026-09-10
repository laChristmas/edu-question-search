"""把 APE / CM17K / Geometry3K / Hendrycks MATH 记录转成题库条目。"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterator

from eqsearch.models import GalleryItem
from eqsearch.text.formula import source_question_text
from eqsearch.text.normalize import equation_template, normalize_text, structure_text, variant_group_id
from eqsearch.vision.diagram import canonicalize_figure, ink_vector
from eqsearch.vision.phash import perceptual_hash

_CJK_SPACE = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")
_GEOMETRY_IMAGES = ("img_diagram.png", "img_diagram.jpg", "img.png", "image.png")
_MATH_SKIP = {"data.json", "logic_form.json", "prompts_4shot.jsonl"}
_MATH_SUBJECTS = {
    "algebra",
    "counting_and_probability",
    "counting & probability",
    "geometry",
    "intermediate_algebra",
    "intermediate algebra",
    "number_theory",
    "number theory",
    "prealgebra",
    "precalculus",
}


def detect_source(path: Path) -> str:
    path = Path(path)
    if path.is_dir():
        if any(path.rglob("data.json")):
            return "geometry3k"
        if _looks_math_tree(path):
            return "math"
        jsons = sorted(p for p in path.rglob("*.json") if p.is_file())
        if not jsons:
            jsonl = sorted(p for p in path.rglob("*.jsonl") if p.is_file())
            if jsonl:
                return detect_source(jsonl[0])
            raise ValueError(f"目录中没有可识别的题目文件：{path}")
        return detect_source(jsons[0])
    if path.suffix.lower() == ".jsonl" or path.name.endswith(".ape.json"):
        raw = _peek_record(path)
        if _is_math_record(raw):
            return "math"
        return "ape"
    raw = _peek_record(path)
    keys = set(raw)
    if _is_math_record(raw):
        return "math"
    if {"annotat_text", "problem_text", "problem_type_graph"} & keys:
        return "geometry3k"
    return "cm17k"


def iter_source_items(path: Path, source: str | None = None, limit: int | None = None) -> Iterator[GalleryItem]:
    path = Path(path)
    source = (source or detect_source(path)).strip().lower()
    n = 0
    if source == "geometry3k":
        for item in _iter_geometry3k(path):
            yield item
            n += 1
            if limit is not None and n >= limit:
                return
        return
    if source == "math":
        for item in _iter_math(path):
            yield item
            n += 1
            if limit is not None and n >= limit:
                return
        return
    if source in ("ape", "cm17k"):
        for raw in iter_json_records(path):
            item = mwp_to_item(raw, source=source)
            if not item.normalized_text:
                continue
            yield item
            n += 1
            if limit is not None and n >= limit:
                return
        return
    raise ValueError(f"未知数据源：{source}")


def iter_json_records(path: Path) -> Iterator[dict]:
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.suffix.lower() in {".json", ".jsonl"} and p.is_file())
        for file in files:
            yield from iter_json_records(file)
        return
    if path.suffix.lower() == ".jsonl" or _looks_jsonl(path):
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        yield rec
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    yield from _records_from_payload(payload)


def mwp_to_item(raw: dict, source: str = "ape") -> GalleryItem:
    text = str(raw.get("original_text") or raw.get("text") or raw.get("segmented_text") or "")
    if source == "cm17k":
        text = _collapse_cjk_spaces(text)
    equation = raw.get("equation")
    structure = structure_text(text)
    raw_id = str(raw.get("id") or raw.get("pid") or "")
    prefix = "cm17k" if source == "cm17k" else "ape"
    if raw_id and source == "cm17k":
        item_id = f"{prefix}-{raw_id}"
    elif raw_id:
        item_id = raw_id
    else:
        item_id = f"{prefix}-{hashlib.sha1(text.encode('utf-8')).hexdigest()[:12]}"
    kind = _mwp_kind(text, str(equation or ""), raw)
    return GalleryItem(
        id=item_id,
        original_text=text,
        normalized_text=normalize_text(text),
        structure_text=structure,
        equation=equation,
        equation_template=equation_template(equation),
        original_cluster_id=item_id,
        variant_group_id=variant_group_id(structure),
        meta={
            "ans": raw.get("ans"),
            "source": source,
            "kind": kind,
            "type": raw.get("type") or raw.get("problem_type"),
        },
    )


def math_to_item(
    raw: dict,
    split: str = "",
    subject: str = "",
    file_id: str = "",
) -> GalleryItem | None:
    """Hendrycks MATH：题干是带 LaTeX 的 problem，不用 solution。Asymptote 源码不进题干，Note 保留。"""
    problem = str(raw.get("problem") or "").strip()
    if not problem:
        return None
    subject = subject or str(raw.get("type") or "unknown")
    split = split or str(raw.get("split") or "")
    fid = str(file_id or raw.get("id") or hashlib.sha1(problem.encode("utf-8")).hexdigest()[:10])
    parts = ["math"]
    if split:
        parts.append(_slug(split))
    parts.append(_slug(subject))
    parts.append(_slug(fid))
    item_id = "-".join(part for part in parts if part)
    stem = source_question_text(problem) or problem
    structure = structure_text(stem)
    return GalleryItem(
        id=item_id,
        original_text=stem,
        normalized_text=normalize_text(stem),
        structure_text=structure,
        original_cluster_id=item_id,
        variant_group_id=variant_group_id(structure),
        meta={
            "ans": boxed_answer(str(raw.get("solution") or "")),
            "source": "math",
            "kind": _math_kind(subject),
            "type": subject,
            "level": raw.get("level"),
            "split": split or None,
            "stem": " ".join(stem.split()),
        },
    )


def boxed_answer(solution: str) -> str | None:
    start = solution.rfind(r"\boxed")
    if start < 0:
        return None
    rest = solution[start + len(r"\boxed") :].lstrip()
    if rest.startswith("{"):
        depth = 0
        for i, char in enumerate(rest):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    inner = rest[1:i].strip()
                    return inner or None
        return None
    match = re.match(r"(\S+)", rest)
    return match.group(1) if match else None


def geometry_stem(raw: dict) -> str:
    """Human-readable problem stem, not logic-form index text."""
    for key in ("problem_text", "annotat_text", "compact_text"):
        value = str(raw.get(key) or "").replace("<image>", "").strip()
        if value:
            return " ".join(value.split())
    return ""


def geometry_index_text(raw: dict) -> str:
    problem = str(raw.get("annotat_text") or raw.get("problem_text") or raw.get("compact_text") or "")
    problem = problem.replace("<image>", "").strip()
    logic = raw.get("logic_form") if isinstance(raw.get("logic_form"), dict) else {}
    parts = [
        problem,
        " ".join(_as_str_list(raw.get("problem_type_graph"))),
        " ".join(_as_str_list(raw.get("problem_type_goal"))),
        " ".join(_as_str_list(logic.get("text_logic_form"))),
        " ".join(_as_str_list(logic.get("diagram_logic_form"))),
    ]
    return " ".join(part for part in parts if part)


def geometry3k_to_item(raw: dict, image_path: Path | None = None) -> GalleryItem | None:
    stem = geometry_stem(raw)
    index_text = geometry_index_text(raw)
    if not index_text.strip():
        return None
    raw_id = str(raw.get("id") if raw.get("id") is not None else image_path.parent.name if image_path else "")
    item_id = f"g3k-{raw_id}" if raw_id else f"g3k-{hashlib.sha1(index_text.encode('utf-8')).hexdigest()[:12]}"
    structure = structure_text(index_text)
    phash = None
    diagram_vector = None
    if image_path and image_path.exists():
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        phash = perceptual_hash(canonicalize_figure(image))
        diagram_vector = ink_vector(image)
    answer = _geometry_answer(raw)
    logic = raw.get("logic_form") if isinstance(raw.get("logic_form"), dict) else {}
    return GalleryItem(
        id=item_id,
        original_text=stem or index_text,
        normalized_text=normalize_text(index_text),
        structure_text=structure,
        original_cluster_id=item_id,
        variant_group_id=variant_group_id(structure),
        phash=phash,
        diagram_vector=diagram_vector,
        meta={
            "ans": answer,
            "source": "geometry3k",
            "kind": "geometry",
            "stem": stem or None,
            "graph": _as_str_list(raw.get("problem_type_graph")),
            "goal": _as_str_list(raw.get("problem_type_goal")),
            "image": str(image_path) if image_path else None,
            "split": raw.get("data_type"),
            "text_logic": _as_str_list(logic.get("text_logic_form")),
        },
    )


def _iter_geometry3k(path: Path) -> Iterator[GalleryItem]:
    path = Path(path)
    if path.is_file():
        for raw in iter_json_records(path):
            item = geometry3k_to_item(raw)
            if item:
                yield item
        return
    seen: set[Path] = set()
    for data_file in sorted(path.rglob("data.json")):
        folder = data_file.parent
        if folder in seen:
            continue
        seen.add(folder)
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            continue
        item = geometry3k_to_item(raw, _geometry_image(folder))
        if item:
            yield item


def _geometry_image(folder: Path) -> Path | None:
    for name in _GEOMETRY_IMAGES:
        candidate = folder / name
        if candidate.exists():
            return candidate
    pngs = sorted(folder.glob("*.png"))
    return pngs[0] if pngs else None


def _geometry_answer(raw: dict) -> str | None:
    answer = raw.get("answer")
    choices = raw.get("choices") or raw.get("compact_choices") or []
    if isinstance(answer, str) and answer in {"A", "B", "C", "D"} and choices:
        idx = "ABCD".index(answer)
        if idx < len(choices):
            return str(choices[idx])
    if answer is not None:
        return str(answer)
    return None


def _iter_math(path: Path) -> Iterator[GalleryItem]:
    path = Path(path)
    if path.is_file():
        if path.name in _MATH_SKIP:
            return
        subject, split = _math_file_meta(path)
        if path.suffix.lower() == ".jsonl" or _looks_jsonl(path):
            for index, raw in enumerate(iter_json_records(path)):
                if not _is_math_record(raw):
                    continue
                item = math_to_item(raw, split=split, subject=subject or str(raw.get("type") or ""), file_id=str(index))
                if item:
                    yield item
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and _is_math_record(raw):
            item = math_to_item(raw, split=split, subject=subject or str(raw.get("type") or ""), file_id=path.stem)
            if item:
                yield item
        return
    for file in sorted(path.rglob("*")):
        if not file.is_file():
            continue
        if file.suffix.lower() not in {".json", ".jsonl"}:
            continue
        if file.name in _MATH_SKIP:
            continue
        yield from _iter_math(file)


def _looks_math_tree(path: Path) -> bool:
    for file in path.rglob("*"):
        if not file.is_file() or file.name in _MATH_SKIP:
            continue
        if file.suffix.lower() not in {".json", ".jsonl"}:
            continue
        try:
            raw = _peek_record(file)
        except ValueError:
            continue
        if _is_math_record(raw):
            return True
    return False


def _is_math_record(raw: dict) -> bool:
    return bool(raw.get("problem") and raw.get("solution") is not None and not raw.get("original_text") and not raw.get("problem_text"))


def _math_kind(subject: str) -> str:
    slug = _slug(subject)
    if "geometry" in slug:
        return "geometry"
    if slug in {"algebra", "intermediate-algebra", "precalculus"} or slug.endswith("calculus"):
        return "function"
    return "algebra"


def _math_file_meta(path: Path) -> tuple[str, str]:
    stem = path.stem.lower()
    split = ""
    subject = ""
    for name in ("train", "test", "valid", "val"):
        suffix = f"_{name}"
        if stem.endswith(suffix):
            split = "train" if name == "train" else "test" if name == "test" else "valid"
            subject = stem[: -len(suffix)].replace("_", " ")
            break
        if name in path.parts:
            split = "train" if name == "train" else "test" if name == "test" else "valid"
    if not subject:
        for part in reversed(path.parts[:-1]):
            if part.lower().replace("_", " ") in _MATH_SUBJECTS or part.lower() in _MATH_SUBJECTS:
                subject = part
                break
    return subject, split


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "-", str(value).strip().lower()).strip("-")
    return text or "x"


def _mwp_kind(text: str, equation: str, raw: dict) -> str:
    typed = str(raw.get("type") or raw.get("problem_type") or "").lower()
    if "non" in typed or "nonlinear" in typed:
        return "function"
    if "方程" in typed or "equation" in typed:
        return "equationset" if "set" in typed or "组" in typed else "algebra"
    if any(token in text for token in ("一次函数", "二次函数", "三次函数", "函数")):
        return "function"
    if "^" in equation or "**" in equation:
        return "function"
    if ";" in equation:
        return "equationset"
    return "algebra"


def _collapse_cjk_spaces(text: str) -> str:
    text = _CJK_SPACE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _as_str_list(value: object) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


def _peek_record(path: Path) -> dict:
    chunk = path.read_bytes()[: 256 * 1024].decode("utf-8", errors="ignore").lstrip()
    decoder = json.JSONDecoder()
    if chunk.startswith("{"):
        obj, _ = decoder.raw_decode(chunk)
        return obj if isinstance(obj, dict) else {}
    if chunk.startswith("["):
        try:
            obj, _ = decoder.raw_decode(chunk)
            if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                return obj[0]
        except json.JSONDecodeError:
            pass
        idx = chunk.find("{")
        if idx >= 0:
            obj, _ = decoder.raw_decode(chunk[idx:])
            return obj if isinstance(obj, dict) else {}
    raise ValueError(f"无法识别数据格式：{path}")


def _looks_jsonl(path: Path) -> bool:
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            if not line.lstrip().startswith("{"):
                return False
            n += 1
            if n >= 3:
                return True
    return n >= 2


def _records_from_payload(payload: object) -> Iterator[dict]:
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                yield item
        return
    if isinstance(payload, dict):
        if any(k in payload for k in ("original_text", "annotat_text", "problem_text", "equation", "problem")):
            yield payload
            return
        for value in payload.values():
            if isinstance(value, dict):
                yield value
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        yield item
