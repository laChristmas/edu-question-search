"""从题干抽取公式跨度，做成可比对的模板。"""

from __future__ import annotations

import re

from eqsearch.text.normalize import equation_template, normalize_text
from eqsearch.text.similarity import structure_similarity

_EQ_HEAD = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Za-z][A-Za-z0-9]*\s*\([^)]{0,48}\)|[A-Za-z][A-Za-z0-9]*)\s*[=＝]\s*"
)
_EQ_STOP = re.compile(
    r"[，。；;？?\n]|(\s+(?:for|when|if|then|where|Find|find|have|does)\b)|(?=[的时求则])"
)
_ABS_EQ = re.compile(
    r"(?:\|[^|]{1,48}\||\[[^\[\]]{1,48}\])\s*[=＝]\s*(?:\|[^|]{1,48}\||\[[^\[\]]{1,48}\])"
)
_OCR_ABS = re.compile(r"(?<!\\)\[([^\[\]]{1,48})\]")
_BEGIN_ENV = re.compile(r"\\begin\{([A-Za-z*]+)\}")
_LATEX_CMD = re.compile(
    r"\\(?:d?frac|tfrac|sqrt|sum|int|log|ln|sin|cos|tan|lim|times|cdot)"
)
_ASY = re.compile(r"\[asy\].*?\[/asy\]", re.I | re.S)
_GAP_PUNCT = re.compile(r"^[\s,;:]+$")
_PLACEHOLDER = " EQ "


def source_question_text(text: str) -> str:
    """题干里的 Asymptote 是作图指令，不是卷面上的字。完整拍照也读不出 draw/label。"""
    if not text:
        return ""
    return _ASY.sub("\n", text).strip()


def extract_formula_spans(text: str) -> list[tuple[int, int, str]]:
    """返回 (start, end, snippet)，下标相对原始字符串。"""
    if not text:
        return []
    text = repair_ocr_math(text)
    raw: list[tuple[int, int]] = []
    raw.extend(_dollar_spans(text))
    raw.extend(_display_math_spans(text))
    raw.extend(_env_spans(text))
    raw.extend(_latex_cmd_spans(text))
    raw.extend(_abs_eq_spans(text))
    raw.extend(_equation_spans(text))
    merged = _merge_spans(raw, text)
    out: list[tuple[int, int, str]] = []
    for start, end in merged:
        for span_s, span_e, snippet in _split_aligned_span(text, start, end):
            if not _counts_as_formula(snippet):
                continue
            snippet = snippet.strip("$ ").strip(" ;,.")
            if len(re.sub(r"\s+", "", snippet)) < 3:
                continue
            out.append((span_s, span_e, snippet))
    return out


def _counts_as_formula(snippet: str) -> bool:
    """点名、线段标注不算公式；方程、分式、根式、函数式才算。"""
    body = snippet.strip().strip("$").strip()
    if len(re.sub(r"\s+", "", body)) < 3:
        return False
    if re.search(r"\\(?:frac|sqrt|sum|int|log|ln|sin|cos|tan|lim|times|cdot)", snippet):
        return True
    if "=" in snippet or "＝" in snippet:
        return True
    if re.search(r"[\[\|].+[\]\|]\s*[=＝]\s*[\[\|]", snippet):
        return True
    if re.search(r"\b(?:sin|cos|tan|log|ln|sqrt)\b", snippet, re.I) and re.search(r"[\(\)\^_]", snippet):
        return True
    return False


def extract_formulas(text: str) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    seen: set[str] = set()
    for _s, _e, snippet in extract_formula_spans(text):
        cleaned = normalize_text(snippet)
        if len(cleaned) < 3 or cleaned in seen:
            continue
        seen.add(cleaned)
        found.append(cleaned)
    return found


def mask_formula_text(text: str, placeholder: str = _PLACEHOLDER) -> str:
    """把公式换成占位，只留叙述，避免和公式通道重复计分。"""
    if not text:
        return ""
    text = source_question_text(text)
    spans = extract_formula_spans(text)
    if not spans:
        return text
    covered = sum(end - start for start, end, _ in spans)
    compact = len(re.sub(r"\s+", "", text))
    if compact and covered >= 0.8 * len(text.strip()):
        return text
    parts: list[str] = []
    cursor = 0
    for start, end, _snippet in spans:
        parts.append(text[cursor:start])
        parts.append(placeholder)
        cursor = end
    parts.append(text[cursor:])
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def formula_template_blob(text: str, equation: str | None = None) -> str | None:
    text = source_question_text(text)
    parts = extract_formulas(text)
    templates: list[str] = []
    seen: set[str] = set()
    for part in parts:
        templ = equation_template(part)
        if templ and templ not in seen:
            seen.add(templ)
            templates.append(templ)
    if equation:
        templ = equation_template(str(equation).strip(" ;,."))
        if templ and templ not in seen:
            templates.append(templ)
    blob = " ".join(templates)
    return blob or None


def formula_atom_templates(text: str) -> list[str]:
    """公式拆成独立行再做模板；aligned 四行和四个 $...$ 能对上。"""
    text = source_question_text(text)
    atoms: list[str] = []
    seen: set[str] = set()
    for _s, _e, snippet in extract_formula_spans(text):
        templ = equation_template(normalize_text(snippet))
        if templ and templ not in seen:
            seen.add(templ)
            atoms.append(templ)
    return atoms


def formulas_compatible(query_blob: str | None, item_blob: str | None, threshold: float) -> bool:
    if not query_blob and not item_blob:
        return True
    if not query_blob or not item_blob:
        return False
    if query_blob == item_blob:
        return True
    if structure_similarity(query_blob, item_blob) >= threshold:
        return True
    q_parts = set(query_blob.split())
    i_parts = set(item_blob.split())
    if q_parts and q_parts == i_parts:
        return True
    compact_q = query_blob.replace(" ", "")
    compact_i = item_blob.replace(" ", "")
    shorter, longer = (compact_q, compact_i) if len(compact_q) <= len(compact_i) else (compact_i, compact_q)
    if len(shorter) >= 12 and shorter in longer:
        return True
    return _ocr_lost_fraction(query_blob, item_blob, threshold)


def repair_ocr_math(text: str) -> str:
    """OCR 常把绝对值竖线认成方括号，并把 Unicode 减号认成别的横线。"""
    text = text.replace("−", "-").replace("–", "-").replace("‐", "-")

    def _bar(match: re.Match[str]) -> str:
        inner = match.group(1)
        if re.search(r"[A-Za-z].*\d|\d.*[A-Za-z]|[+\-]", inner):
            return f"|{inner}|"
        return match.group(0)

    return _OCR_ABS.sub(_bar, text)


def _dollar_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "$":
            i += 1
            continue
        if i + 1 < n and text[i + 1] == "$":
            j = text.find("$$", i + 2)
            if j < 0:
                break
            spans.append((i, j + 2))
            i = j + 2
            continue
        j = text.find("$", i + 1)
        if j < 0:
            break
        spans.append((i, j + 1))
        i = j + 1
    return spans


def _display_math_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        start = text.find(r"\[", i)
        if start < 0:
            break
        end = text.find(r"\]", start + 2)
        if end < 0:
            break
        spans.append((start, end + 2))
        i = end + 2
    return spans


def _env_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _BEGIN_ENV.finditer(text):
        name = match.group(1)
        end_token = r"\end{" + name + "}"
        end = text.find(end_token, match.end())
        if end < 0:
            continue
        spans.append((match.start(), end + len(end_token)))
    return spans


def _latex_cmd_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _LATEX_CMD.finditer(text):
        end = _consume_latex_tail(text, match.end())
        if end > match.end():
            spans.append((match.start(), end))
    return spans


def _consume_latex_tail(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i < n and text[i] == "[":
        close = text.find("]", i + 1)
        if close < 0:
            return i
        i = close + 1
        while i < n and text[i].isspace():
            i += 1
    groups = 0
    while i < n and text[i] == "{":
        close = _matching_brace(text, i)
        if close < 0:
            break
        i = close + 1
        groups += 1
        while i < n and text[i].isspace():
            i += 1
        if groups >= 2:
            break
    return i


def _matching_brace(text: str, i: int) -> int:
    if i >= len(text) or text[i] != "{":
        return -1
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return j
    return -1


def _abs_eq_spans(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _ABS_EQ.finditer(text)]


def _ocr_lost_fraction(query: str, item: str, threshold: float) -> bool:
    """拍照 OCR 常把叠式分式压成只剩分母多项式。"""
    item_rhs = item.split("=", 1)[-1]
    query_rhs = query.split("=", 1)[-1]
    if "/" not in item_rhs or "/" in query_rhs:
        return False
    parts = re.search(r"\(([^()/]+)/([^()]+)\)", item_rhs)
    if not parts:
        return False
    return structure_similarity(query_rhs, parts.group(2)) >= 0.80


def _equation_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for match in _EQ_HEAD.finditer(text):
        start = match.start()
        rest = text[match.end() :]
        stop = _EQ_STOP.search(rest)
        end = match.end() + (stop.start() if stop else min(len(rest), 96))
        if end - start >= 3:
            spans.append((start, end))
    return spans


def _split_aligned_span(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
    snippet = text[start:end]
    if not re.search(r"\\begin\{align", snippet):
        return [(start, end, snippet.strip())]
    rows: list[tuple[int, int, str]] = []
    cursor = 0
    row_start = start
    while True:
        br = snippet.find("\\\\", cursor)
        if br < 0:
            piece = text[row_start:end].strip()
            if piece:
                rows.append((row_start, end, piece))
            break
        abs_br = start + br
        piece = text[row_start:abs_br].strip()
        if piece:
            rows.append((row_start, abs_br, piece))
        row_start = abs_br + 2
        cursor = br + 2
    return rows or [(start, end, snippet.strip())]


def _merge_spans(spans: list[tuple[int, int]], text: str = "") -> list[tuple[int, int]]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda item: (item[0], -item[1]))
    merged: list[tuple[int, int]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_s, prev_e = merged[-1]
        gap = text[prev_e:start] if text else ""
        if start <= prev_e + 1 or (gap and _GAP_PUNCT.fullmatch(gap)):
            merged[-1] = (prev_s, max(prev_e, end))
        else:
            merged.append((start, end))
    return merged
