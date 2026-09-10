from PIL import Image, ImageDraw

from eqsearch.pipeline.ingest import ingest_records
from eqsearch.pipeline.search import prepare_query, search, search_without_formula
from eqsearch.models import GalleryItem
from eqsearch.text.normalize import normalize_text, structure_text, variant_group_id
from eqsearch.vision.phash import perceptual_hash


def _item(item_id: str, text: str, phash: str | None = None) -> GalleryItem:
    structure = structure_text(text)
    return GalleryItem(
        id=item_id,
        original_text=text,
        normalized_text=normalize_text(text),
        structure_text=structure,
        original_cluster_id=item_id,
        variant_group_id=variant_group_id(structure),
        phash=phash,
    )


CIRCLE_A = "一个圆形花坛的半径是4米，现在要扩建花坛，将半径增加1米，这时花坛的占地面积增加了多少。"
CIRCLE_B = "一个圆形花坛的半径是9米，现在要扩建花坛，将半径增加2米，这时花坛的占地面积增加了多少。"
DONATE = "五年级同学参加义务捐书活动，五1班捐了500本，五2班捐的本数是五1班80%。"
AGE = "妈妈今年40岁，是小芳的4倍，小芳今年多少岁。"
SPEED = "一辆汽车的行驶速度为60千米/时，甲乙两地的距离是180千米，从甲地开往乙地需要几时？"
SCHOOL = "学校把135本练习本平均分给3个班，每班多少本？"
MONITOR = "班长把1860本练习册平均分给10个人，每人多少本？"
SCHOOL_VARIANT = "学校把248本练习本平均分给4个班，每班多少本？"


def _gallery():
    return ingest_records(
        [
            _item("circle-a", CIRCLE_A),
            _item("circle-b", CIRCLE_B),
            _item("donate", DONATE),
            _item("age", AGE),
            _item("speed", SPEED),
            _item("school", SCHOOL),
        ]
    )


def test_original_query_returns_itself_first():
    gallery = _gallery()
    resp = search(gallery, text=CIRCLE_A)
    ids = [c.item.id for c in resp.results]
    assert "circle-a" in ids
    assert resp.results[0].item.id == "circle-a"
    assert resp.results[0].relation == "original"
    assert resp.originals >= 1
    assert len(resp.results) <= 3


def test_original_query_also_returns_variant():
    gallery = _gallery()
    resp = search(gallery, text=CIRCLE_A)
    ids = [c.item.id for c in resp.results]
    assert "circle-a" in ids
    assert "circle-b" in ids
    assert next(c for c in resp.results if c.item.id == "circle-b").relation == "variant"


def test_variant_query_returns_original_and_template_neighbor():
    gallery = _gallery()
    resp = search(gallery, text=CIRCLE_B)
    by_id = {c.item.id: c for c in resp.results}
    assert "circle-b" in by_id
    assert by_id["circle-b"].relation == "original"
    assert "circle-a" in by_id
    assert by_id["circle-a"].relation == "variant"


def test_same_operation_different_story_is_not_returned():
    gallery = _gallery()
    resp = search(gallery, text=MONITOR)
    assert all(c.item.id != "school" for c in resp.results)
    assert all(c.relation != "same_type" for c in resp.results)


def test_true_variant_is_returned():
    gallery = _gallery()
    resp = search(gallery, text=SCHOOL_VARIANT)
    ids = [c.item.id for c in resp.results]
    assert "school" in ids
    school = next(c for c in resp.results if c.item.id == "school")
    assert school.relation == "variant"


def test_never_returns_more_than_three():
    gallery = _gallery()
    resp = search(gallery, text=DONATE)
    assert len(resp.results) <= 3


def test_without_formula_pipeline_returns_original_and_variant():
    gallery = _gallery()
    resp = search_without_formula(gallery, text=CIRCLE_A)
    assert resp.math_ocr is False
    assert resp.results
    assert resp.results[0].item.id == "circle-a"
    assert resp.results[0].relation == "original"
    assert resp.results[0].formula_score == 0.0
    assert any(c.item.id == "circle-b" and c.relation == "variant" for c in resp.results)
    query = prepare_query(text="已知 y=2x+3，当 x=4 时求 y", math_ocr=False)
    assert query.use_formula is False
    assert query.equation_template is None
    with_formula = prepare_query(text="已知 y=2x+3，当 x=4 时求 y", math_ocr=True)
    assert with_formula.use_formula is True
    assert with_formula.equation_template


def test_full_photo_similarity_is_not_used_as_original():
    """Background-matched photos of different stems must not count as the same problem."""
    clutter_a = Image.new("RGB", (96, 96), "white")
    ImageDraw.Draw(clutter_a).rectangle((4, 4, 24, 24), fill="navy")
    ImageDraw.Draw(clutter_a).polygon([(30, 80), (60, 20), (90, 80)], outline="black")
    clutter_b = Image.new("RGB", (96, 96), "white")
    ImageDraw.Draw(clutter_b).rectangle((4, 4, 24, 24), fill="navy")
    ImageDraw.Draw(clutter_b).ellipse((28, 18, 92, 82), outline="black")
    gallery = ingest_records(
        [
            _item("photo", CIRCLE_A, phash=perceptual_hash(clutter_a)),
            _item("age", AGE),
        ]
    )
    drifted = CIRCLE_A.replace("4米", "8米").replace("增加1米", "增加7米")
    resp = search(gallery, text=drifted, image=clutter_a)
    by_id = {c.item.id: c for c in resp.results}
    if "photo" in by_id:
        assert by_id["photo"].relation != "original"


def test_same_stem_and_cropped_figure_match_despite_clutter():
    from eqsearch.vision.diagram import canonicalize_figure, ink_vector
    from eqsearch.vision.layout import extract_diagram_crops

    clean = Image.new("RGB", (160, 160), "white")
    ImageDraw.Draw(clean).polygon([(20, 140), (80, 20), (140, 140)], outline="black")
    photo = Image.new("RGB", (280, 220), "white")
    ImageDraw.Draw(photo).rectangle((2, 2, 26, 26), fill="navy")
    ImageDraw.Draw(photo).polygon([(70, 180), (140, 40), (210, 180)], outline="black")
    crops = extract_diagram_crops(photo, [])
    assert crops
    gallery = ingest_records(
        [
            GalleryItem(
                id="fig",
                original_text=SCHOOL,
                normalized_text=normalize_text(SCHOOL),
                structure_text=structure_text(SCHOOL),
                original_cluster_id="fig",
                variant_group_id=variant_group_id(structure_text(SCHOOL)),
                phash=perceptual_hash(canonicalize_figure(clean)),
                diagram_vector=ink_vector(clean),
            ),
            _item("age", AGE),
        ]
    )
    resp = search(gallery, text=SCHOOL, image=photo)
    assert resp.has_diagram
    assert resp.results
    assert resp.results[0].item.id == "fig"
    assert resp.results[0].relation == "original"


def test_same_stem_different_attached_figure_is_not_original():
    from eqsearch.vision.diagram import canonicalize_figure, ink_vector

    tri = Image.new("RGB", (120, 120), "white")
    ImageDraw.Draw(tri).polygon([(10, 110), (60, 10), (110, 110)], outline="black")
    circ = Image.new("RGB", (120, 120), "white")
    ImageDraw.Draw(circ).ellipse((12, 12, 108, 108), outline="black", width=3)
    gallery = ingest_records(
        [
            GalleryItem(
                id="tri",
                original_text=SCHOOL,
                normalized_text=normalize_text(SCHOOL),
                structure_text=structure_text(SCHOOL),
                original_cluster_id="tri",
                variant_group_id=variant_group_id(structure_text(SCHOOL)),
                phash=perceptual_hash(canonicalize_figure(tri)),
                diagram_vector=ink_vector(tri),
            ),
        ]
    )
    resp = search(gallery, text=SCHOOL, image=circ)
    assert all(c.relation != "original" or c.item.id != "tri" for c in resp.results)

