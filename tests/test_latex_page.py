import sys
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "data" / "eval"
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from latex_page import escape_percents, geometry_to_latex, prepare_body, strip_asy


def test_strip_asy_keeps_stem():
    raw = r'If $PQ$ is a line, find $x$. [asy] size(150); draw((0,0)--(1,0)); [/asy] Extra.'
    out = strip_asy(raw)
    assert "[asy]" not in out.lower()
    assert "draw" not in out
    assert "find $x$" in out
    assert "Extra." in out


def test_geometry_wraps_angle_and_frac():
    wrapped = geometry_to_latex(r"Find m \angle S.")
    assert r"$\angle$" in wrapped or r"$\angle S$" in wrapped
    frac = geometry_to_latex(r"If \frac { I J } { X J } = 2, find x.")
    assert r"$\frac" in frac


def test_prepare_math_keeps_dollars_and_escapes_percent():
    body = prepare_body(r"What is 50% of $\frac{1}{3}$ of 36?", "math")
    assert r"50\%" in body
    assert r"$\frac{1}{3}$" in body
