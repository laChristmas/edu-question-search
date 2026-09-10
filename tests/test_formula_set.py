import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "data" / "eval"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from formula_set import image_path, parse_sources, safe_name


def test_safe_name_strips_path_chars():
    assert "/" not in safe_name("test/algebra/1006")
    assert safe_name("test/algebra/1006") == "test_algebra_1006"


def test_image_path_is_per_source():
    path = image_path("geometry3k", "1149")
    assert path.parts[-3] == "geometry3k"
    assert path.parts[-2] == "images"
    assert path.name == "1149.png"
    math_path = image_path("math", "test/algebra/1006")
    assert math_path.parts[-3] == "math"
    assert math_path.name == "test_algebra_1006.png"


def test_parse_sources_all_and_subset():
    assert parse_sources("all") == ("ape", "cm17k", "geometry3k", "math")
    assert parse_sources("math,geometry3k") == ("math", "geometry3k")
