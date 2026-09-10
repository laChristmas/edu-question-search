from pathlib import Path

from eqsearch.models import GalleryItem, ScoredCandidate, SearchResponse
from eqsearch.pipeline.eval_metrics import parse_image_manifest, score_response, substitute_numbers
from eqsearch.pipeline.ingest import ingest_records
from eqsearch.pipeline.search import search
from eqsearch.text.normalize import normalize_text, structure_text, variant_group_id


def test_substitute_changes_numbers():
    src = "半径是4米，增加1米"
    out = substitute_numbers(src)
    assert out is not None
    assert out != src
    assert structure_text(src) == structure_text(out)


def test_cutoff_allows_empty():
    items = [
        GalleryItem(
            id="a",
            original_text="甲乙两数的差和商都是6．那么甲乙两数的和是多少？",
            normalized_text=normalize_text("甲乙两数的差和商都是6．那么甲乙两数的和是多少？"),
            structure_text=structure_text("甲乙两数的差和商都是6．那么甲乙两数的和是多少？"),
            variant_group_id=variant_group_id(structure_text("甲乙两数的差和商都是6．那么甲乙两数的和是多少？")),
        ),
        GalleryItem(
            id="b",
            original_text="用1、2、3、4、5、6、7、8、9这9个数字排成一个最小的能被11整除的九位数。",
            normalized_text=normalize_text("用1、2、3、4、5、6、7、8、9这9个数字排成一个最小的能被11整除的九位数。"),
            structure_text=structure_text("用1、2、3、4、5、6、7、8、9这9个数字排成一个最小的能被11整除的九位数。"),
            variant_group_id="other",
        ),
    ]
    gallery = ingest_records(items)
    resp = search(gallery, text="完全不相关的英语句子 about photosynthesis.")
    assert len(resp.results) <= 3


def _cand(item_id: str, original: bool) -> ScoredCandidate:
    text = f"题 {item_id}"
    item = GalleryItem(
        id=item_id,
        original_text=text,
        normalized_text=normalize_text(text),
        structure_text=structure_text(text),
    )
    return ScoredCandidate(
        item=item,
        retrieval_score=0.9,
        surface=0.9,
        structure=0.9,
        is_original=original,
        relation="original" if original else "variant",
        final_score=1.2,
    )


def test_score_response_tracks_first_and_extra_originals():
    gold_first = SearchResponse(query_text="q", results=[_cand("gold", True), _cand("other", True)])
    scored = score_response(gold_first, "gold")
    assert scored["hit"] and scored["first"] and scored["gold_original"]
    assert scored["extra_originals"] == 1
    gold_second = SearchResponse(query_text="q", results=[_cand("other", True), _cand("gold", True)])
    scored = score_response(gold_second, "gold")
    assert scored["hit"] and not scored["first"]
    assert score_response(SearchResponse(query_text="q", results=[]), "gold")["empty"]


def test_run_eval_text_gold_is_first():
    from eqsearch.pipeline.eval_metrics import run_eval

    items = [
        GalleryItem(
            id="a",
            original_text="半径是4米，周长是多少？",
            normalized_text=normalize_text("半径是4米，周长是多少？"),
            structure_text=structure_text("半径是4米，周长是多少？"),
            variant_group_id=variant_group_id(structure_text("半径是4米，周长是多少？")),
        ),
        GalleryItem(
            id="b",
            original_text="用1、2、3、4、5这五个数字排成最小的五位数。",
            normalized_text=normalize_text("用1、2、3、4、5这五个数字排成最小的五位数。"),
            structure_text=structure_text("用1、2、3、4、5这五个数字排成最小的五位数。"),
            variant_group_id="other",
        ),
    ]
    report = run_eval(ingest_records(items), limit=2, seed=0, math_ocr=False)
    assert report["samples"] == 2
    assert report["original_hit_rate"] == 1.0
    assert report["original_first_rate"] == 1.0
    assert report["gold_marked_original_rate"] == 1.0
    assert report["false_extra_original_rate"] == 0.0


def test_parse_image_manifest(tmp_path: Path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"")
    (tmp_path / "manifest.txt").write_text("shot.png\tmath-test-algebra-2\n", encoding="utf-8")
    pairs = parse_image_manifest(tmp_path)
    assert pairs == [(png, "math-test-algebra-2")]
