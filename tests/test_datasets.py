from pathlib import Path
import json

from PIL import Image, ImageDraw

from eqsearch.datasets.loaders import boxed_answer, detect_source, geometry_index_text, iter_source_items
from eqsearch.pipeline.ingest import ingest_sources
from eqsearch.pipeline.search import search

ROOT = Path(__file__).resolve().parent / "fixtures"
CM17K = ROOT / "cm17k_sample.json"
G3K = ROOT / "geometry3k"
MATH = ROOT / "math"


def test_detect_cm17k_and_geometry3k():
    assert detect_source(CM17K) == "cm17k"
    assert detect_source(G3K) == "geometry3k"


def test_detect_math_json_and_jsonl():
    assert detect_source(MATH) == "math"
    assert detect_source(MATH / "train" / "algebra" / "1.json") == "math"
    assert detect_source(MATH / "prealgebra_test.jsonl") == "math"


def test_cm17k_keeps_function_kind_and_readable_text():
    items = list(iter_source_items(CM17K, source="cm17k"))
    by_id = {item.id: item for item in items}
    func = by_id["cm17k-f1"]
    assert "一次函数" in func.original_text
    assert func.meta["kind"] == "function"
    assert by_id["cm17k-a1"].meta["kind"] == "algebra"


def test_math_uses_problem_not_solution():
    items = list(iter_source_items(MATH, source="math"))
    by_id = {item.id: item for item in items}
    algebra = by_id["math-train-algebra-1"]
    assert algebra.meta["kind"] == "function"
    assert algebra.meta["ans"] == "30"
    assert "eqsearch" in algebra.original_text
    assert "SOLUTIONONLYXYZ" not in algebra.original_text
    assert "SOLUTIONONLYXYZ" not in algebra.normalized_text
    pre = by_id["math-test-prealgebra-0"]
    assert pre.meta["kind"] == "algebra"
    assert pre.meta["ans"] == "2"


def test_boxed_answer_nested_braces():
    assert boxed_answer(r"done. \boxed{\dfrac{1}{2}}") == r"\dfrac{1}{2}"
    assert boxed_answer(r"\boxed 42") == "42"
    assert boxed_answer("no box") is None


def test_geometry3k_indexes_diagram_logic(tmp_path: Path):
    folder = tmp_path / "2401"
    folder.mkdir()
    (folder / "data.json").write_text((G3K / "12" / "data.json").read_text(encoding="utf-8"), encoding="utf-8")
    img = Image.new("RGB", (64, 64), "white")
    ImageDraw.Draw(img).polygon([(8, 56), (32, 8), (56, 56)], outline="black")
    img.save(folder / "img_diagram.png")
    item = list(iter_source_items(folder, source="geometry3k"))[0]
    assert item.id == "g3k-12"
    assert item.original_text == "Find x."
    assert "$" not in item.original_text
    assert item.meta["kind"] == "geometry"
    assert item.phash
    assert item.diagram_vector
    assert "LengthOf" in item.structure_text or "NUM" in item.structure_text


def test_merged_ingest_can_search_function_geometry_and_math():
    gallery = ingest_sources(
        [
            (CM17K, "cm17k"),
            (G3K, "geometry3k"),
            (MATH, "math"),
        ]
    )
    sources = {item.meta.get("source") for item in gallery.items}
    assert sources == {"cm17k", "geometry3k", "math"}
    func = search(gallery, text="已知一次函数y=2x+3，当x=4时，y的值是多少？")
    assert func.results
    assert func.results[0].item.id == "cm17k-f1"
    raw = json.loads((G3K / "12" / "data.json").read_text(encoding="utf-8"))
    geo = search(gallery, text=geometry_index_text(raw))
    assert geo.results
    assert geo.results[0].item.id == "g3k-12"
    assert geo.results[0].item.meta.get("source") == "geometry3k"
    math_hit = search(
        gallery,
        text=r"Let $g_{\mathrm{eqsearch}}(x)=x^{2}+3x+2$. Evaluate $g_{\mathrm{eqsearch}}(4)$.",
    )
    assert math_hit.results
    assert math_hit.results[0].item.id == "math-train-algebra-1"
    assert math_hit.results[0].item.meta.get("source") == "math"
