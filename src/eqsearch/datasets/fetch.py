"""Download CM17K, Geometry3K, and Hendrycks MATH into a local directory."""

from __future__ import annotations

import tarfile
import urllib.request
import zipfile
from pathlib import Path

CM17K_FILES = {
    "questions.json": "https://raw.githubusercontent.com/QinJinghui/NS-Solver/main/dataset/cm17k/questions.json",
}

GEOMETRY3K_ZIPS = {
    "train.zip": "https://github.com/lupantech/InterGPS/raw/main/data/geometry3k/train.zip",
    "val.zip": "https://github.com/lupantech/InterGPS/raw/main/data/geometry3k/val.zip",
    "test.zip": "https://github.com/lupantech/InterGPS/raw/main/data/geometry3k/test.zip",
}

MATH_TAR_URLS = (
    "https://people.eecs.berkeley.edu/~hendrycks/MATH.tar",
    "https://huggingface.co/datasets/qwedsacf/competition_math/resolve/main/MATH.tar",
)

MATH_SUBJECTS = (
    "algebra",
    "counting_and_probability",
    "geometry",
    "intermediate_algebra",
    "number_theory",
    "prealgebra",
    "precalculus",
)

MATH_JSONL_TMPL = "https://huggingface.co/datasets/HuggingFaceTB/MATH/resolve/main/data/{subject}_{split}.jsonl"

DATASETS = ("cm17k", "geometry3k", "math")


def fetch_dataset(name: str, dest: Path, splits: tuple[str, ...] | None = None) -> Path:
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    key = name.strip().lower().replace("_", "-")
    if key in {"hendrycks-math", "hendrycksmath", "competition-math"}:
        key = "math"
    if key == "cm17k":
        for filename, url in CM17K_FILES.items():
            _download(url, dest / filename)
        return dest
    if key == "geometry3k":
        wanted = splits or ("train", "val", "test")
        for split in wanted:
            zip_name = f"{split}.zip"
            url = GEOMETRY3K_ZIPS[zip_name]
            archive = dest / zip_name
            _download(url, archive)
            _unzip(archive, dest / split)
        return dest
    if key == "math":
        wanted = tuple(s for s in (splits or ("train", "test")) if s in {"train", "test"})
        if not wanted:
            wanted = ("train", "test")
        if _math_ready(dest, wanted):
            return dest
        try:
            _fetch_math_jsonl(dest, wanted)
        except Exception:
            pass
        if _math_jsonl_complete(dest, wanted):
            return dest
        _clear_partial_math_jsonl(dest, wanted)
        archive = dest / "MATH.tar"
        last_error: Exception | None = None
        for url in MATH_TAR_URLS:
            try:
                _download(url, archive)
                _untar(archive, dest)
                if _math_ready(dest, wanted):
                    return dest
            except Exception as exc:
                last_error = exc
        raise RuntimeError(f"无法下载 Hendrycks MATH：{last_error}")
    raise ValueError(f"未知数据集：{name}（可选：{', '.join(DATASETS)}）")


def _math_ready(dest: Path, splits: tuple[str, ...] | None = None) -> bool:
    wanted = tuple(s for s in (splits or ("train", "test")) if s in {"train", "test"}) or ("train", "test")
    if _math_jsonl_complete(dest, wanted):
        return True
    n = 0
    for path in dest.rglob("*.json"):
        if path.name in {"data.json", "logic_form.json"}:
            continue
        n += 1
        if n >= 100:
            return True
    return False


def _math_jsonl_complete(dest: Path, splits: tuple[str, ...]) -> bool:
    found = {path.name: path for path in dest.rglob("*.jsonl")}
    for subject in MATH_SUBJECTS:
        for split in splits:
            name = f"{subject}_{split}.jsonl"
            path = found.get(name)
            if path is None or not _looks_json_payload(path):
                return False
    return True


def _clear_partial_math_jsonl(dest: Path, splits: tuple[str, ...]) -> None:
    needed = {f"{subject}_{split}.jsonl" for subject in MATH_SUBJECTS for split in splits}
    for path in dest.rglob("*.jsonl"):
        if path.name in needed:
            path.unlink(missing_ok=True)


def _looks_json_payload(path: Path) -> bool:
    try:
        chunk = path.read_bytes()[:2048].lstrip()
    except OSError:
        return False
    return bool(chunk) and chunk[:1] in {b"{", b"["}


def _fetch_math_jsonl(dest: Path, splits: tuple[str, ...]) -> None:
    for subject in MATH_SUBJECTS:
        for split in splits:
            name = f"{subject}_{split}.jsonl"
            _download(MATH_JSONL_TMPL.format(subject=subject, split=split), dest / name)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": "eqsearch"})
    with urllib.request.urlopen(request, timeout=180) as resp, tmp.open("wb") as fh:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            fh.write(chunk)
    tmp.replace(dest)


def _unzip(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.rglob("data.json")):
        return
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(dest)


def _untar(archive: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    if _math_ready(dest, ("train", "test")):
        return
    with tarfile.open(archive) as tf:
        tf.extractall(dest)
