from eqsearch.text.normalize import equation_template, normalize_text, structure_text


def test_normalize_strips_space_and_punct():
    assert normalize_text("半径是 4 米，") == "半径是4米,"


def test_normalize_strips_math_piecewise_latex():
    latex = r"""Let \[f(x) = \left\{
\begin{array}{cl} ax+3, &\text{ if }x>2, \\
x-5 &\text{ if } -2 \le x \le 2, \\
2x-b &\text{ if } x <-2.
\end{array}
\right.\]Find $a+b$."""
    plain = "Let f(x)=ax+3, if x>2, x-5 if -2<=x<=2, 2x-b if x<-2. Find a+b."
    assert "array" not in normalize_text(latex)
    assert normalize_text(latex) == normalize_text(plain)


def test_normalize_keeps_sqrt_and_degree_words():
    latex = r"What is the range of $y=\log_2 (\sqrt{\sin x})$ for $0^\circ< x < 180^\circ$?"
    plain = "What is the range of y=log_2 (sqrt(sin x)) for 0 degrees < x < 180 degrees?"
    assert normalize_text(latex) == normalize_text(plain)


def test_normalize_strips_geometry_latex():
    latex = r"Circle $O$ has a radius of 13 inches. Radius $\overline{O B}$ is perpendicular to chord $C D$ which is 24 inches long. Find $O X$."
    plain = "Circle O has a radius of 13 inches. Radius O B is perpendicular to chord C D which is 24 inches long. Find O X."
    assert normalize_text(latex) == normalize_text(plain)


def test_structure_masks_quantities_keeps_type_words():
    text = "二次函数y=2x**2+3，五年级有20人"
    struct = structure_text(text)
    assert "二次函数" in struct
    assert "五年级" in struct
    assert "20" not in struct
    assert "2x" not in struct or "NUM" in struct
    assert "NUM" in struct


def test_variant_shares_structure():
    a = "一个圆形花坛的半径是4米，现在要扩建花坛，将半径增加1米"
    b = "一个圆形花坛的半径是9米，现在要扩建花坛，将半径增加2米"
    assert structure_text(a) == structure_text(b)
    assert normalize_text(a) != normalize_text(b)


def test_equation_template():
    assert equation_template("x=150*20%/5%-150") == equation_template("x=80*10%/2%-80")
