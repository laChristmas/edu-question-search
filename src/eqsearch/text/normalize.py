"""文本规范化：去 LaTeX、去空白、数量打成 NUM。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_PUNCT = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "；": ";",
        "：": ":",
        "？": "?",
        "！": "!",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "「": '"',
        "」": '"',
        "『": '"',
        "』": '"',
        "、": ",",
        "．": ".",
        "—": "-",
        "～": "~",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "　": " ",
        "×": "*",
        "÷": "/",
        "＊": "*",
        "＝": "=",
        "−": "-",
        "–": "-",
        "‐": "-",
    }
)

_LATEX_FRAC = re.compile(r"\\(?:d|t)?frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}")
_LATEX_SQRT = re.compile(r"\\sqrt\s*\{([^{}]+)\}")
_LATEX_LEFT_RIGHT = re.compile(r"\\(left|right)\.?")
_LATEX_ENV = re.compile(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?")
_LATEX_BRACE_CMD = re.compile(r"\\[a-zA-Z]+\*?\{([^{}]*)\}")
_LATEX_CMD = re.compile(r"\\[a-zA-Z]+\*?")
_MATH_DOLLARS = re.compile(r"\$+")
_SPACES = re.compile(r"\s+")
_LATEX_SYMBOLS = (
    (r"\leq", "<="),
    (r"\geq", ">="),
    (r"\le", "<="),
    (r"\ge", ">="),
    (r"\neq", "!="),
    (r"\cdots", "..."),
    (r"\dotsb", "..."),
    (r"\ldots", "..."),
    (r"^\circ", "degrees"),
    (r"\circ", "o"),
    (r"\sin", "sin"),
    (r"\cos", "cos"),
    (r"\tan", "tan"),
    (r"\log", "log"),
    (r"\ln", "ln"),
)

# Keep problem-type words that contain digits/Chinese numerals from being treated as quantities.
_PROTECT = re.compile(
    "|".join(
        [
            r"一次函数",
            r"二次函数",
            r"三次函数",
            r"一次式",
            r"二次式",
            r"一元一次方程",
            r"一元二次方程",
            r"二元一次方程组",
            r"二元一次方程",
            r"[一二三四五六七八九]年级",
            r"[两一二三四五六七八九十]位数",
            r"第[一二三四五六七八九十零〇\d]+[天步次条项问]",
        ]
    )
)

_MIXED_FRACTION = re.compile(r"\d+\(\s*\d+\s*/\s*\d+\s*\)")
_PAREN_FRACTION = re.compile(r"\(\s*\d+\s*/\s*\d+\s*\)")
_SLASH_FRACTION = re.compile(r"\d+\s*/\s*\d+")
_PERCENT = re.compile(r"\d+(?:\.\d+)?%")
_DECIMAL = re.compile(r"\d+\.\d+")
_INTEGER = re.compile(r"\d+")
_MULTI_NUM = re.compile(r"(?:NUM)+")
_QTY = re.compile(r"\d+(?:\.\d+)?%?")


def quantity_tokens(text: str) -> tuple[tuple[str, float], ...]:
    tokens: list[tuple[str, float]] = []
    for raw in _QTY.findall(normalize_text(text)):
        if raw.endswith("%"):
            tokens.append(("pct", round(float(raw[:-1]), 6)))
        else:
            tokens.append(("n", round(float(raw), 6)))
    return tuple(tokens)


def quantities_equal(a: str, b: str) -> bool:
    return quantity_tokens(a) == quantity_tokens(b)


def _strip_latex(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _LATEX_FRAC.sub(r"(\1/\2)", text)
        text = _LATEX_SQRT.sub(r"sqrt(\1)", text)
        text = _LATEX_ENV.sub(" ", text)
        text = _LATEX_BRACE_CMD.sub(r"\1", text)
    text = _LATEX_LEFT_RIGHT.sub("", text)
    for src, dst in _LATEX_SYMBOLS:
        text = text.replace(src, dst)
    text = _LATEX_CMD.sub("", text)
    text = _MATH_DOLLARS.sub("", text)
    text = text.replace(r"\[", " ").replace(r"\]", " ")
    text = text.replace("&", " ")
    text = text.replace("{", "").replace("}", "").replace("\\", "")
    return text


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_PUNCT)
    text = _strip_latex(text)
    text = _SPACES.sub("", text)
    return text.strip()


def structure_text(text: str) -> str:
    """Replace quantities with NUM; keep 二次函数-style type words intact."""
    normalized = normalize_text(text)
    if not normalized:
        return ""
    protected: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"§{'Q' * len(protected)}§"

    stashed = _PROTECT.sub(_stash, normalized)
    stashed = _MIXED_FRACTION.sub("NUM", stashed)
    stashed = _PAREN_FRACTION.sub("NUM", stashed)
    stashed = _SLASH_FRACTION.sub("NUM", stashed)
    stashed = _PERCENT.sub("NUM", stashed)
    stashed = _DECIMAL.sub("NUM", stashed)
    stashed = _INTEGER.sub("NUM", stashed)
    stashed = _MULTI_NUM.sub("NUM", stashed)
    for i, token in reversed(list(enumerate(protected))):
        stashed = stashed.replace(f"§{'Q' * (i + 1)}§", token)
    return stashed


def equation_template(equation: str | None) -> str | None:
    if not equation:
        return None
    templ = structure_text(equation)
    return templ or None


def variant_group_id(structure: str) -> str:
    digest = hashlib.sha1(structure.encode("utf-8")).hexdigest()[:16]
    return f"vg_{digest}"
