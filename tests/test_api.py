from pathlib import Path

from PIL import Image

from eqsearch.api.app import _image_url, _result_payload
from eqsearch.index.gallery import item_image_path, item_stem_text
from eqsearch.models import GalleryItem, ScoredCandidate
from eqsearch.text.normalize import normalize_text, structure_text


def _item(item_id: str, image: str | None = None) -> GalleryItem:
    return GalleryItem(
        id=item_id,
        original_text="Find x.",
        normalized_text=normalize_text("Find x."),
        structure_text=structure_text("Find x."),
        meta={"source": "geometry3k", "kind": "geometry", "image": image},
    )


def test_item_image_path_requires_existing_image(tmp_path: Path):
    missing = _item("a", str(tmp_path / "nope.png"))
    assert item_image_path(missing) is None
    img = tmp_path / "ok.png"
    Image.new("RGB", (8, 8), "white").save(img)
    found = _item("b", str(img))
    assert item_image_path(found) == img
    assert _image_url(found) == "/v1/items/b/image"
    assert _image_url(missing) is None


def test_result_payload_includes_image_url(tmp_path: Path):
    img = tmp_path / "fig.png"
    Image.new("RGB", (8, 8), "white").save(img)
    cand = ScoredCandidate(
        item=_item("g3k-12", str(img)),
        retrieval_score=0.9,
        surface=1.0,
        structure=1.0,
        final_score=1.2,
        relation="original",
    )
    payload = _result_payload(cand)
    assert payload["id"] == "g3k-12"
    assert payload["image"] == "/v1/items/g3k-12/image"
    assert payload["text"] == "Find x."
    assert payload["formula"] == 0.0
    assert _result_payload(cand, use_formula=False)["formula"] is None
    text_only = ScoredCandidate(
        item=_item("ape-1"),
        retrieval_score=0.5,
        surface=0.5,
        structure=0.5,
    )
    assert _result_payload(text_only)["image"] is None


def test_result_text_uses_geometry_problem_stem(tmp_path: Path):
    folder = tmp_path / "2402"
    folder.mkdir()
    (folder / "data.json").write_text(
        (
            '{"id": 2402, "problem_text": "Circle O has a radius of 13 inches. Find O X.",'
            ' "annotat_text": "Circle $O$ has a radius of 13 inches. Find $OX$."}'
        ),
        encoding="utf-8",
    )
    img = folder / "img_diagram.png"
    Image.new("RGB", (8, 8), "white").save(img)
    cand = ScoredCandidate(
        item=_item("g3k-2402", str(img)),
        retrieval_score=0.9,
        surface=1.0,
        structure=1.0,
        final_score=1.2,
        relation="original",
    )
    cand.item.original_text = "Circle $O$ has a radius of 13 inches. Find $OX$ Circle Length"
    assert item_stem_text(cand.item) == "Circle O has a radius of 13 inches. Find O X."
    assert _result_payload(cand)["text"] == "Circle O has a radius of 13 inches. Find O X."

