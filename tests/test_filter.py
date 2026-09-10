from eqsearch.config import SearchConfig
from eqsearch.models import GalleryItem, QueryRecord, ScoredCandidate
from eqsearch.pipeline.filter_original import mark_originals
from eqsearch.pipeline.variant import tag_variant
from eqsearch.text.formula import formula_template_blob
from eqsearch.text.normalize import normalize_text, structure_text
from eqsearch.text.similarity import structure_similarity, surface_similarity


def _cand(text: str, query: str) -> ScoredCandidate:
    return ScoredCandidate(
        item=GalleryItem(
            id="x",
            original_text=text,
            normalized_text=normalize_text(text),
            structure_text=structure_text(text),
        ),
        retrieval_score=0.8,
        surface=surface_similarity(normalize_text(query), normalize_text(text)),
        structure=structure_similarity(structure_text(query), structure_text(text)),
    )


def test_same_text_is_original():
    q = "鸡兔同笼，共有274只脚．已知鸡比兔多23只，则鸡有多少只．"
    query = QueryRecord(text=q, normalized_text=normalize_text(q), structure_text=structure_text(q))
    kept, count = mark_originals(query, [_cand(q, q)], SearchConfig())
    assert count == 1
    assert kept[0].is_original
    assert kept[0].relation == "original"


def test_number_rewrite_is_variant_not_original():
    q = "一个圆形花坛的半径是4米，现在要扩建花坛，将半径增加1米"
    other = "一个圆形花坛的半径是9米，现在要扩建花坛，将半径增加2米"
    query = QueryRecord(text=q, normalized_text=normalize_text(q), structure_text=structure_text(q))
    cand = _cand(other, q)
    kept, count = mark_originals(query, [cand], SearchConfig())
    assert count == 0
    tagged = tag_variant(kept[0], SearchConfig(), query=query)
    assert tagged.is_variant
    assert tagged.relation == "variant"


def test_unrelated_not_variant():
    q = "鸡兔同笼，共有274只脚．已知鸡比兔多23只，则鸡有多少只．"
    other = "爷爷今年62岁，东东今年8岁，明年爷爷的年龄是东东的几倍？"
    cand = _cand(other, q)
    tagged = tag_variant(cand, SearchConfig(), query=QueryRecord(text=q, normalized_text=normalize_text(q), structure_text=structure_text(q)))
    assert not tagged.is_variant
    assert tagged.relation == "unrelated"


STEM_LOG = r"What is the range of y=\log_2(\sqrt{\sin x}) for 0<x<180?"


def test_formula_mismatch_blocks_original_when_formula_on():
    query = QueryRecord(
        text=STEM_LOG,
        normalized_text=normalize_text(STEM_LOG),
        structure_text=structure_text(STEM_LOG),
        equation_template="f(x)=x+NUM",
        use_formula=True,
    )
    kept, count = mark_originals(query, [_cand(STEM_LOG, STEM_LOG)], SearchConfig())
    assert count == 0
    assert not kept[0].is_original


def test_without_formula_original_is_stem_and_diagram_only():
    query = QueryRecord(
        text=STEM_LOG,
        normalized_text=normalize_text(STEM_LOG),
        structure_text=structure_text(STEM_LOG),
        equation_template="f(x)=x+NUM",
        use_formula=False,
    )
    kept, count = mark_originals(query, [_cand(STEM_LOG, STEM_LOG)], SearchConfig())
    assert count == 1
    assert kept[0].is_original
    assert kept[0].formula_score == 0.0


def test_formula_pipeline_same_equation_is_original():
    query = QueryRecord(
        text=STEM_LOG,
        normalized_text=normalize_text(STEM_LOG),
        structure_text=structure_text(STEM_LOG),
        use_formula=True,
    )
    kept, count = mark_originals(query, [_cand(STEM_LOG, STEM_LOG)], SearchConfig())
    assert count == 1
    assert kept[0].is_original


def test_ocr_abs_and_flattened_frac_still_hit_original():
    abs_q = "What is the smallest value of x such that [5x - 1] = [3x + 2]? Express your answer as a common fraction."
    abs_item = r"What is the smallest value of $x$ such that $|5x - 1| = |3x + 2|$? Express your answer as a common fraction."
    query = QueryRecord(
        text=abs_q,
        normalized_text=normalize_text(abs_q),
        structure_text=structure_text(abs_q),
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(query, [_cand(abs_item, abs_q)], SearchConfig())
    assert count == 1
    frac_q = "How many vertical asymptotes does the graph of y = x2+x-6 have?"
    frac_item = r"How many vertical asymptotes does the graph of $y=\frac{2}{x^2+x-6}$ have?"
    other = r"How many vertical asymptotes does the graph of $y=\frac{x-3}{x^2+7x-30}$ have?"
    q2 = QueryRecord(
        text=frac_q,
        normalized_text=normalize_text(frac_q),
        structure_text=structure_text(frac_q),
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(q2, [_cand(frac_item, frac_q)], SearchConfig())
    assert count == 1
    kept, count = mark_originals(q2, [_cand(other, frac_q)], SearchConfig())
    assert count == 0


def test_vl_vector_and_norm_queries_match_gold():
    gold_cross = (
        r"Given $\mathbf{a} = \begin{pmatrix} 2 \\ 1 \\ 0 \end{pmatrix},$ "
        r"$\mathbf{b} = \begin{pmatrix} 0 \\ 0 \\ 1 \end{pmatrix},$ and "
        r"$\mathbf{c} = \begin{pmatrix} 1 \\ -2 \\ -3 \end{pmatrix},$ compute "
        r"\[(\mathbf{a} \times \mathbf{b}) \times \mathbf{c} - \mathbf{a} \times (\mathbf{b} \times \mathbf{c}).\]"
    )
    vl_cross = (
        r"Given $ \mathbf{a} = \begin{pmatrix} 2 \\ 1 \\ 0 \end{pmatrix} $, "
        r"$ \mathbf{b} = \begin{pmatrix} 0 \\ 0 \\ 1 \end{pmatrix} $, and "
        r"$ \mathbf{c} = \begin{pmatrix} 1 \\ -2 \\ -3 \end{pmatrix} $, compute "
        r"$ (\mathbf{a} \times \mathbf{b}) \times \mathbf{c} - \mathbf{a} \times (\mathbf{b} \times \mathbf{c}). $"
    )
    q_cross = QueryRecord(
        text=vl_cross,
        normalized_text=normalize_text(vl_cross),
        structure_text=structure_text(vl_cross),
        equation_template=formula_template_blob(vl_cross) + " " + formula_template_blob(vl_cross).replace(" ", ""),
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(q_cross, [_cand(gold_cross, vl_cross)], SearchConfig())
    assert count == 1
    gold_uv = (
        r"Let $\mathbf{u}$ and $\mathbf{v}$ be vectors such that $\|\mathbf{u}\| = \|\mathbf{v}\| = 2$ "
        r"and $\mathbf{u} \cdot \mathbf{v} = -1.$  If $\theta$ is the angle between the vectors "
        r"$\mathbf{u} + \mathbf{v}$ and $2 \mathbf{u} - \mathbf{v},$ then find $\cos \theta.$"
    )
    vl_uv = (
        r"Let $ \mathbf{u} $ and $ \mathbf{v} $ be vectors such that $ \|\mathbf{u}\| = \|\mathbf{v}\| = 2 $ "
        r"and $ \mathbf{u} \cdot \mathbf{v} = -1 $. If $ \theta $ is the angle between the vectors "
        r"$ \mathbf{u} + \mathbf{v} $ and $ 2\mathbf{u} - \mathbf{v} $, then find $ \cos\theta $."
    )
    doubled = formula_template_blob(vl_uv)
    q_uv = QueryRecord(
        text=vl_uv,
        normalized_text=normalize_text(vl_uv),
        structure_text=structure_text(vl_uv),
        equation_template=f"{doubled} {doubled.replace(' ', '')}",
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(q_uv, [_cand(gold_uv, vl_uv)], SearchConfig())
    assert count == 1
    gold_tri = r"In triangle $ABC,$ \[a^4 + b^4 + c^4 = 2c^2 (a^2 + b^2).\]Enter the possible values of $\angle C,$ in degrees, separated by commas."
    q_tri = r"In triangle $ABC,$ $a^4 + b^4 + c^4 = 2c^2 (a^2 + b^2).$ Enter the possible values of $\angle C,$ in degrees, separated by commas."
    qt = QueryRecord(
        text=q_tri,
        normalized_text=normalize_text(q_tri),
        structure_text=structure_text(q_tri),
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(qt, [_cand(gold_tri, q_tri)], SearchConfig())
    assert count == 1
    gold_pq = r'If $PQ$ is a straight line, what is the value of $x$? [asy] size(150); draw((-1,0)--(1,0)); label("$x^\circ$",(0,0)); [/asy]'
    q_pq = r"If $PQ$ is a straight line, what is the value of $x$?"
    qp = QueryRecord(
        text=q_pq,
        normalized_text=normalize_text(q_pq),
        structure_text=structure_text(q_pq),
        use_formula=True,
        from_image=True,
    )
    kept, count = mark_originals(qp, [_cand(gold_pq, q_pq)], SearchConfig())
    assert count == 1


def test_same_narrative_different_formula_is_not_original():
    q = "求函数 y=sin x 的值域"
    other = "求函数 y=cos x 的值域"
    query = QueryRecord(
        text=q,
        normalized_text=normalize_text(q),
        structure_text=structure_text(q),
        use_formula=True,
    )
    kept, count = mark_originals(query, [_cand(other, q)], SearchConfig())
    assert count == 0
    assert not kept[0].is_original
