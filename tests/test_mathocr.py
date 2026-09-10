from PIL import Image, ImageDraw

from eqsearch.models import QueryRecord
from eqsearch.pipeline.search import prepare_query
from eqsearch.text.formula import (
    extract_formula_spans,
    extract_formulas,
    formula_template_blob,
    formulas_compatible,
    mask_formula_text,
)
from eqsearch.vision.layout import OcrLine
from eqsearch.vision.mathocr import (
    looks_like_formula,
    merge_line_with_latex,
    merge_stem_with_latex,
    parse_math_ocr_flag,
    recognize_math_lines,
    should_math_ocr_line,
)
from eqsearch.vision.ocr import OcrBackend, OcrResult


def test_looks_like_formula_detects_functions_not_prose():
    assert looks_like_formula("Let f(x)=x+1 and g(x)=2x")
    assert looks_like_formula(r"y=\log_2(\sqrt{\sin x})")
    assert looks_like_formula("x^2 + 3x + 2 = 0")
    assert not looks_like_formula("Find the area of the square.")
    assert not looks_like_formula("O")
    assert not should_math_ocr_line(
        "What is the range of the function y = log_2 ( sqrt(sin x) ) for 0 degrees < x < 180 degrees?"
    )
    assert should_math_ocr_line(r"y=\log_2(\sqrt{\sin x})")
    assert should_math_ocr_line("f(x)=(1+x)/(1-x)")


def test_merge_line_appends_latex_once():
    assert merge_line_with_latex("Let f(x)=x+1", r"f(x)=x+1") == "Let f(x)=x+1"
    merged = merge_line_with_latex("range of the function", r"\log_2(\sqrt{\sin x})")
    assert r"\log_2" in merged
    assert merge_line_with_latex("range of y", r"\mathrm{W/nat~is~trange~furcthor}") == "range of y"


def test_extract_formulas_keeps_math_ocr_latex():
    text = r"What is the range $ \log_2(\sqrt{\sin x}) $ for x?"
    found = extract_formulas(text)
    assert any("log" in f or "sin" in f or "sqrt" in f for f in found)
    blob = formula_template_blob("range of y", equation=r"\log_2(\sqrt{\sin x})")
    assert blob
    nested = extract_formulas(r"Find y=\frac{1}{1+\frac{1}{x}}")
    assert nested
    mixed = extract_formulas("What is the range of y = log_2 ( sqrt(sin x) ) for 0 degrees < x < 180 degrees?")
    assert any("log" in f or "sin" in f for f in mixed)
    geo = extract_formulas(
        r"Circle $O$ has a radius of 13 inches. Radius $\overline{O B}$ is perpendicular to chord $C D$."
    )
    assert geo == []
    masked = mask_formula_text("求函数 y=sin x 的值域")
    assert "EQ" in masked
    assert "sin" not in masked
    assert formulas_compatible(None, None, 0.82)
    assert not formulas_compatible("y=NUMx+NUM", None, 0.82)
    assert not formulas_compatible(None, "y=NUMx+NUM", 0.82)
    ocr_line = "How many vertical asymptotes does the graph of y = x2+x-6 have?"
    snippets = [s for _a, _b, s in extract_formula_spans(ocr_line)]
    assert snippets
    assert all("have" not in s.lower() for s in snippets)
    q_abs = "such that [5x - 1] = [3x + 2]?"
    item_abs = r"such that $|5x - 1| = |3x + 2|$?"
    assert formula_template_blob(q_abs)
    assert formulas_compatible(formula_template_blob(q_abs), formula_template_blob(item_abs), 0.82)
    display = r"In triangle $ABC,$ \[a^4 + b^4 + c^4 = 2c^2 (a^2 + b^2).\] Enter the possible values of $\angle C.$"
    assert formula_template_blob(display)
    assert "a^NUM" in (formula_template_blob(display) or "")
    asy = r'If $PQ$ is a straight line, what is the value of $x$? [asy] size(150); draw((0,0)--(1,0)); [/asy]'
    from eqsearch.text.formula import source_question_text

    assert "[asy]" not in source_question_text(asy)
    assert "straight line" in source_question_text(asy)
    noted = r"Let $M_n$ be a matrix. Find \[\sum_{n=1}^{\infty} \frac{1}{8D_n+1}.\]Note: The determinant of $[a]$ is $a$."
    assert "Note" in source_question_text(noted)
    assert "8D_n" in source_question_text(noted)
    aligned = r"Determine $w^2+x^2$ if \[\begin{aligned} \frac{x^2}{2^2-1}+\frac{w^2}{2^2-7^2}&= 1 \\ \frac{x^2}{4^2-1}+\frac{w^2}{4^2-7^2} &= 1 \end{aligned}\]"
    inline = r"Determine $w^2+x^2$ if $\frac{x^2}{2^2-1}+\frac{w^2}{2^2-7^2}=1$, $\frac{x^2}{4^2-1}+\frac{w^2}{4^2-7^2}=1$."
    assert formulas_compatible(formula_template_blob(inline), formula_template_blob(aligned), 0.82)


def test_parse_math_ocr_flag(monkeypatch):
    monkeypatch.delenv("EQSEARCH_MATH_OCR", raising=False)
    assert parse_math_ocr_flag(None) is True
    assert parse_math_ocr_flag("") is True
    assert parse_math_ocr_flag("0") is False
    assert parse_math_ocr_flag("false") is False
    assert parse_math_ocr_flag("off") is False
    assert parse_math_ocr_flag("1") is True
    assert parse_math_ocr_flag(False) is False
    assert parse_math_ocr_flag(True) is True
    monkeypatch.setenv("EQSEARCH_MATH_OCR", "0")
    assert parse_math_ocr_flag(None) is False
    assert parse_math_ocr_flag("") is False
    assert parse_math_ocr_flag("1") is True


def test_recognize_math_lines_disabled_skips_engine():
    called = []
    img = Image.new("RGB", (240, 48), "white")
    lines = [OcrLine("f(x)=x+1", (4, 4, 220, 40))]
    found = recognize_math_lines(
        img,
        lines,
        engine=lambda crop: called.append(crop) or r"f(x)=x+1",
        enabled=False,
    )
    assert found == {}
    assert called == []


def test_recognize_math_lines_uses_injected_engine():
    img = Image.new("RGB", (240, 48), "white")
    ImageDraw.Draw(img).text((8, 12), "f(x)=x+1", fill="black")
    lines = [OcrLine("Let f(x)=x+1", (4, 4, 220, 40))]
    found = recognize_math_lines(img, lines, engine=lambda _crop: r"f(x)=x+1")
    assert found[0] == r"f(x)=x+1"
    text = merge_stem_with_latex(lines, found)
    assert "Let f(x)=x+1" in text


def test_recognize_math_lines_crops_mixed_english_span():
    called = []
    img = Image.new("RGB", (400, 40), "white")
    line = OcrLine(
        "What is the range of y=log_2(sqrt(sin x)) for 0<x<180?",
        (0, 0, 400, 36),
    )
    found = recognize_math_lines(
        img,
        [line],
        engine=lambda crop: called.append(crop.size) or r"\log_2(\sqrt{\sin x})",
    )
    assert called
    assert found
    assert r"\log_2" in found[0]


class _LatexOcr(OcrBackend):
    def recognize(self, image: Image.Image, math_ocr: bool | None = None) -> OcrResult:
        return OcrResult(
            text=r"What is the range of y=log_2(sqrt(sin x)) $\log_2(\sqrt{\sin x})$",
            latex=r"\log_2(\sqrt{\sin x})",
            backend="fake-math",
        )


def test_prepare_query_uses_math_ocr_latex():
    img = Image.new("RGB", (32, 32), "white")
    query = prepare_query(text="", image=img, ocr=_LatexOcr())
    assert "log_2" in query.text or "sin" in query.text
    assert query.equation_template
    assert query.ocr_ok
    # keep QueryRecord usable
    assert isinstance(query, QueryRecord)
    skipped = prepare_query(text="", image=img, ocr=_LatexOcr(), math_ocr=False)
    assert skipped.use_formula is False
    assert skipped.equation_template is None


def test_clean_reader_text_keeps_latex_drops_solution():
    from eqsearch.vision.read_question import clean_reader_text

    raw = "```markdown\n题目：图象有多少条垂直渐近线 $y=\\frac{2}{x^2+x-6}$\n解答：两条\n```"
    out = clean_reader_text(raw)
    assert r"\frac" in out
    assert "解答" not in out
    assert "两条" not in out
    paren = clean_reader_text(r"求 \(x^2+1\) 的值")
    assert "$x^2+1$" in paren


def test_apply_vision_read_replaces_garbled_stem(monkeypatch):
    from eqsearch.vision import read_question as rq

    monkeypatch.setattr(
        rq,
        "read_question_image",
        lambda _img: rq.ReadResult(
            text=r"How many vertical asymptotes does $y=\frac{2}{x^2+x-6}$ have?",
            latex="y=(NUM/x^NUM+x-NUM)",
            backend="fake",
        ),
    )
    img = Image.new("RGB", (8, 8), "white")
    text, latex = rq.apply_vision_read(img, "y=x2+x-6 have", True)
    assert r"\frac" in text
    assert latex
    stem, empty = rq.apply_vision_read(img, "y=x2+x-6 have", False)
    assert stem == "y=x2+x-6 have"
    assert empty == ""


def test_parse_vision_reader_kind(monkeypatch):
    from eqsearch.vision.read_question import parse_vision_reader_kind

    monkeypatch.delenv("EQSEARCH_VISION_READER", raising=False)
    assert parse_vision_reader_kind(None) == "auto"
    assert parse_vision_reader_kind("off") == "off"
    assert parse_vision_reader_kind("qwen") == "qwen"
    assert parse_vision_reader_kind("paddleocr-vl") == "paddleocr-vl"


def test_fit_vl_image_caps_long_side():
    from eqsearch.vision.read_question import fit_vl_image

    big = Image.new("RGB", (4000, 3000), "white")
    fitted = fit_vl_image(big, max_side=1024)
    assert max(fitted.size) == 1024
    assert fitted.size[0] == 1024
    small = Image.new("RGB", (200, 100), "white")
    assert fit_vl_image(small, max_side=1024).size == (200, 100)


def test_paddle_vl_to_text_ignores_raw_dict_dump():
    from eqsearch.vision.read_question import _paddle_vl_to_text

    dumped = {
        "input_path": "tmp.png",
        "parsing_res_list": [],
        "layout_det_res": {"boxes": []},
    }
    assert _paddle_vl_to_text(dumped) == ""
    filled = {
        "markdown": {"markdown_texts": r"$y=\frac{2}{x}$ have?"},
        "parsing_res_list": [
            {"block_label": "text", "block_content": r"$y=\frac{2}{x}$ have?"},
            {"block_label": "image", "block_content": "skip"},
        ],
    }
    assert r"\frac" in _paddle_vl_to_text(filled)
    assert "skip" not in _paddle_vl_to_text({"parsing_res_list": filled["parsing_res_list"]})
