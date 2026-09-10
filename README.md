# 变式题检索（eqsearch）

Upload a problem photo. Returns the **original first**, then **variants**, at most **3**. Matches the question (stem ∧ formula ∧ figure), not the photo background. Same operation with a different story is not a variant.

教育场景的**拍照搜题**：用户只上传题目照片，返回**原题优先、然后变式，最多 3 条**。匹配的是题目本身，不是照片背景。同一运算、不同故事（例如都是平均分配，但题面完全不同）**不算变式**。

<!--
GitHub About (≤350 chars):
Educational question search from a photo. Originals first, then variants (max 3). Matches stem, formula, and figure — not photo background.

Topics: education, ocr, math, question-search, fastapi
-->

## 项目描述

eqsearch 是面向中小学与竞赛数学的**原题 / 变式检索**服务。部署时用户**只上传题目照片**。系统不是答题模型，也不是用整张照片外观做通用以图搜图。

流程：照片 → RapidOCR 框字并裁题内附图 →（默认）PaddleOCR-VL 或 Qwen2.5-VL 整图抄题并写出 LaTeX → 与题库对齐，最多返回 3 条。

- **原题**：公式检测开时为题干叙述 ∧ 公式模板 ∧ 题内附图；关时为题干 ∧ 附图。缺图则附图项视为通过。
- **变式**：结构相同、数量不同。短题干配不同图（如「求 x」「求阴影面积」）视为无关，不返回。
- **不返回**：无关题、仅题型相近、或分数低于阈值。

附图只用 16×16 墨迹网格和 pHash，不使用 CLIP / GME。题库可合入 APE、CM17K、Geometry3K、Hendrycks MATH。服务为 FastAPI（`POST /v1/search` 上传图片）。

更完整的模块说明、算法与部署硬件见 [docs/项目报告.md](docs/项目报告.md)。评测数字与各部分失败例子见 [docs/测试报告.md](docs/测试报告.md)。

## 匹配规则

检索按开关走两条管线，都不比较照片背景。

**不带公式检测**（`--no-math-ocr` / 页面关闭「公式检测」）：识题干、裁题内附图。原题 = **题干 ∧ 附图**。题干里的式子只当普通文字（数量打成 `NUM` 后比结构）。精排不加公式分。缺图时附图项视为通过。

**带公式检测**（默认）：开源视觉模型**整图读题**（题干 + 公式写成 LaTeX），RapidOCR 只用来框文字、裁附图。原题 = **题干叙述 ∧ 公式模板 ∧ 附图**。两边都没有公式才视为公式通过；只有一侧抽到公式则不算原题。不用解答过程里的方程。缺图时附图项视为通过。读图模型未装时退回普通文字 OCR，不再裁块跑 RapidLaTeXOCR。

| 关系 | 不带公式检测 | 带公式检测 |
|---|---|---|
| `original` | 题干、附图对齐 | 题干、公式、附图对齐 |
| `variant` | 结构相同、数量不同 | 同左 |
| 不返回 | 无关题、仅题型相近、或分数低于阈值 | 同左 |

Geometry3K 接口里的 `text` 是数据集里的 **`problem_text` 原始题干**，不是带 `$...$` 的标注，也不是 logic form 索引文本。有配图的题目会带 `image` 地址。Hendrycks MATH 的 `text` 是带 LaTeX 的 `problem` 题干，不用 `solution` 做匹配。

## 环境

Python **3.11+**。请用项目目录下的 `.venv`，不要用 Anaconda。

```powershell
cd d:\Github\edu-question-search
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\pip install -e ".[dev]"
```

可选：`.[faiss]` 加速向量检索，`.[sbert]` 换句向量编码器。默认是 TF-IDF，一般不必装。

OCR 默认 **RapidOCR + ONNX** 识文字框（关公式检测时也当题干）。公式检测开启时用开源模型**整图读题**：优先 **PaddleOCR-VL 1.6**（需 `paddlepaddle-gpu` 与 `pip install -e ".[paddle-vl]"`），否则 **Qwen2.5-VL-3B**（`pip install -e ".[vlm]"` 并自备 PyTorch）。环境变量 `EQSEARCH_VISION_READER` 可设为 `paddleocr-vl` / `qwen` / `off`。权重默认从百度 BOS 下载到 `~/.paddlex`，首次较慢。不要填 `ocr=paddle`，除非本机另装了 PaddleOCR 当文字框引擎。

公式检测默认开。检索页有 **公式检测** 开关（记在浏览器 `localStorage`）；命令行 `--no-math-ocr` 走「题干 ∧ 附图」管线；HTTP 表单字段 `math_ocr` 为 `1`/`0`。未传该字段时，环境变量 `EQSEARCH_MATH_OCR=0` 可作为服务端默认关闭。

## 数据与入库

| 来源 | 说明 | 题目 ID |
|---|---|---|
| APE | 应用题 JSONL，示例在 `data_example/` | 原始 `id` |
| CM17K | 中文数学题 | `cm17k-{id}` |
| Geometry3K | 几何题 + `img_diagram.png` | `g3k-{id}` |
| Hendrycks MATH | 英文竞赛题（LaTeX 题干，不用解答匹配） | `math-{split}-{subject}-{id}` |

下载 CM17K / Geometry3K / Hendrycks MATH（落到 gitignore 的 `data/raw/`）：

```powershell
.\.venv\Scripts\python -m eqsearch fetch cm17k --out data\raw\cm17k
.\.venv\Scripts\python -m eqsearch fetch geometry3k --out data\raw\geometry3k
.\.venv\Scripts\python -m eqsearch fetch math --out data\raw\math
```

合并入库：

```powershell
.\.venv\Scripts\python -m eqsearch ingest `
  --ape data_example\valid.ape.json `
  --cm17k data\raw\cm17k `
  --geometry3k data\raw\geometry3k `
  --math data\raw\math `
  --out data\index
```

`--limit` 可只导入前 N 条，便于试跑。索引目录默认 gitignore。

## 启动服务

```powershell
.\.venv\Scripts\python -m eqsearch serve --index data\index --port 8000
```

浏览器打开 <http://127.0.0.1:8000/>，上传题目照片。命令行：

```powershell
.\.venv\Scripts\python -m eqsearch search --index data\index --image path\to\question.png
.\.venv\Scripts\python -m eqsearch search --index data\index --image path\to\question.png --no-math-ocr
```

请上传**题干 + 配图**的整题照片。只传 Geometry3K 的 `img_diagram.png`（几乎没有题干）时读不出文字，会空结果。可用 `data\sample_queries\geometry\` 下已验证过的样图。复杂函数（分段、复合、反函数、对数三角）可用 `data\sample_queries\math\` 下的试卷图。

## HTTP 接口

### `POST /v1/search`

`multipart/form-data`，部署接口以图片为准：

- `image`：题目照片（必填）
- `ocr`：默认 `auto`（RapidOCR 框字、裁附图）
- `math_ocr`：`1`/`0`（或 `true`/`false`）。`1` 走公式检测管线；`0` 只比识出的题干和附图，结果里 `formula` 为 `null`。未传时看环境变量 `EQSEARCH_MATH_OCR`
- 公式检测开时，`formula_engine` 表示开源读图模型是否可用

返回摘要（`query_text` 为识图结果，不是用户输入）：

```json
{
          "query_text": "从照片识别出的题干",
  "has_diagram": true,
          "math_ocr": true,
          "formula_engine": true,
  "originals": 1,
  "recalled": 80,
  "reranked": 1,
  "results": [
    {
      "id": "g3k-2402",
      "text": "Circle O has a radius of 13 inches. ...",
      "relation": "original",
      "source": "geometry3k",
      "kind": "geometry",
      "image": "/v1/items/g3k-2402/image",
      "final_score": 1.28,
      "surface": 0.71,
      "structure": 0.69,
      "formula": 0.0,
      "diagram": 0.73
    }
  ]
}
```

无配图的 APE / CM17K / MATH 条目 `image` 为 `null`。

### 其它

- `GET /` 检索页
- `GET /health` 索引规模与来源统计
- `GET /v1/items/{id}/image` 题目配图（仅本地有图的条目）

## 代码结构

```
src/eqsearch/
  cli.py                 # ingest / fetch / search / eval / serve
  config.py              # 召回、原题/变式阈值
  models.py              # 题库条目、查询、打分结果
  api/                   # FastAPI 与静态页
  pipeline/
    ingest.py            # 离线入库
    search.py            # 识图 → 召回 → 原题/变式 → 截断
    filter_original.py   # 原题：题干 ∧ 公式 ∧ 附图
    variant.py           # 变式标注（排除短题干+不同图）
    rerank.py            # 原题在前，最多 3 条
  datasets/              # APE / CM17K / Geometry3K / Hendrycks MATH
  text/                  # 规范化、公式、相似度
  vision/                # RapidOCR 文字框、开源 VLM 读题、附图裁剪
  encode/                # TF-IDF（默认，稠密）/ SBERT
  index/                 # 题库与向量
```

检索流水线：`prepare_query` → `recall` → `mark_originals` → `tag_variants` → `rerank` → `cutoff`。`search()` 按公式检测开关分流到 `search_with_formula` / `search_without_formula`。

阈值在 `SearchConfig`：`t_same` 原题题干、`t_var` 变式结构、`t_formula` 公式、`t_diagram` 附图、`max_results=3`。改阈值后一般不必重新入库；改附图向量或编码器则需要重新 `ingest`。

## 评估成功率

部署指标是**拍照检索**：渲染题图走完整识图管线（有 `manifest.txt` 时列为 `文件名<TAB>题目id`）。

```powershell
.\.venv\Scripts\python -m eqsearch eval --index data\index --images data\sample_queries\math
```

输出：`original_hit_rate`（金标是否出现在最多 3 条里）、`original_first_rate`（是否排第一）、`gold_marked_original_rate`（是否标成原题）、`false_extra_original_rate`（是否还误标了别的原题）、空结果率与时延。公式检测开时较慢。`--no-math-ocr` 可关掉公式检测对比。万级评测与失败例子见 [docs/测试报告.md](docs/测试报告.md)，原始分源结果在 `data/eval/formula_10k/`。

## 测试

```powershell
.\.venv\Scripts\python -m pytest tests -q
```
