from PIL import Image, ImageDraw

from eqsearch.config import SearchConfig
from eqsearch.models import GalleryItem, QueryRecord, ScoredCandidate
from eqsearch.pipeline.filter_original import is_original
from eqsearch.text.formula import extract_formulas, formulas_compatible
from eqsearch.text.normalize import normalize_text, structure_text
from eqsearch.vision.diagram import canonicalize_figure, ink_vector
from eqsearch.vision.layout import OcrLine, extract_diagram_crops, stem_text
from eqsearch.vision.phash import perceptual_hash


def test_stem_text_drops_diagram_labels():
    lines = [
        OcrLine("Circle O has a radius of 13 inches.", (10, 8, 400, 32)),
        OcrLine("Find O X.", (10, 36, 120, 56)),
        OcrLine("O", (80, 140, 92, 154)),
        OcrLine("CBD", (40, 90, 88, 108)),
    ]
    text = stem_text(lines)
    assert "13 inches" in text
    assert "CBD" not in text
    assert text.count("O") < 4


def test_latex_geometry_stem_matches_plain_ocr():
    latex = r"Circle $O$ has a radius of 13 inches. Radius $\overline{O B}$ is perpendicular to chord $C D$ which is 24 inches long. Find $O X$."
    ocr = "Circle O has a radius of 13 inches. Radius O B is perpendicular to chord C D which is 24 inches long. Find O X."
    tri = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(tri).polygon([(8, 90), (50, 8), (92, 90)], outline="black")
    item = GalleryItem(
        id="g3k",
        original_text=latex,
        normalized_text=normalize_text(latex + " FindLength"),
        structure_text=structure_text(latex),
        phash=perceptual_hash(canonicalize_figure(tri)),
        diagram_vector=ink_vector(tri),
    )
    query = QueryRecord(
        text=ocr,
        normalized_text=normalize_text(ocr),
        structure_text=structure_text(ocr),
        phash=item.phash,
        diagram_vector=item.diagram_vector,
        has_diagram=True,
    )
    cand = ScoredCandidate(item=item, retrieval_score=0.9, surface=0.7, structure=0.7)
    assert is_original(query, cand, SearchConfig())


def test_extract_formulas_from_stem():
    text = "已知一次函数 y = 2x + 3，当 x = 4 时求 y"
    found = extract_formulas(text)
    assert any("2" in f and "3" in f for f in found)
    assert formulas_compatible("y=NUMx+NUM", "y=NUMx+NUM", 0.82)


def test_clutter_is_not_kept_as_the_diagram():
    img = Image.new("RGB", (300, 220), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle((4, 4, 22, 22), fill="navy")
    draw.polygon([(70, 180), (150, 40), (230, 180)], outline="black")
    crops = extract_diagram_crops(img, [])
    assert crops
    crop = crops[0]
    assert crop.size[0] > 40 and crop.size[1] > 40
    assert crop.size[0] < 280


def test_original_requires_stem_and_figure_together():
    tri = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(tri).polygon([(8, 90), (50, 8), (92, 90)], outline="black")
    circ = Image.new("RGB", (100, 100), "white")
    ImageDraw.Draw(circ).ellipse((10, 10, 90, 90), outline="black")
    stem = "求图中x的值。"
    item = GalleryItem(
        id="g",
        original_text=stem,
        normalized_text=normalize_text(stem),
        structure_text=structure_text(stem),
        phash=perceptual_hash(canonicalize_figure(tri)),
        diagram_vector=ink_vector(tri),
    )
    query = QueryRecord(
        text=stem,
        normalized_text=normalize_text(stem),
        structure_text=structure_text(stem),
        phash=perceptual_hash(canonicalize_figure(circ)),
        diagram_vector=ink_vector(circ),
        has_diagram=True,
    )
    cand = ScoredCandidate(item=item, retrieval_score=0.9, surface=1.0, structure=1.0)
    assert not is_original(query, cand, SearchConfig())
    query.phash = item.phash
    query.diagram_vector = item.diagram_vector
    assert is_original(query, cand, SearchConfig())
