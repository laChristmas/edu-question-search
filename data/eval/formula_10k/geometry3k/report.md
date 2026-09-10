# formula_10k / geometry3k

- 样本：797
- 文本金标公式检测：**关**
- 图搜公式检测：**关**（题干 ∧ 附图；RapidOCR，不跑读题模型）

### 文本金标

| 分组 | 样本 | 命中@3 | 首位 | 标成原题 | 误标其他原题 | 空结果 | 均返回 | 均耗时s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 797 | 58.3% | 52.6% | 58.3% | 55.0% | 0.0% | 1.82 | 0.33 |
| geometry | 797 | 58.3% | 52.6% | 58.3% | 55.0% | 0.0% | 1.82 | 0.33 |

### 文本失败样例

未命中 332，命中但非首位 46，命中但未标原题 0，另标其他原题 438。

**未命中（最多 15 条）**

- `g3k-1006` (geometry3k) Find x.
  - top3: g3k-1829:original/1.247, g3k-793:original/1.245, g3k-2957:original/1.245
- `g3k-102` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-2231:original/1.287
- `g3k-1028` (geometry3k) Find R S.
  - top3: g3k-2216:original/1.254
- `g3k-1040` (geometry3k) Find m \angle R.
  - top3: g3k-481:original/1.259, g3k-2489:original/1.249, g3k-2123:original/1.247
- `g3k-1050` (geometry3k) Find x.
  - top3: g3k-1829:original/1.247, g3k-793:original/1.245, g3k-2957:original/1.245
- `g3k-1075` (geometry3k) Find A B.
  - top3: g3k-313:original/1.253, g3k-2956:original/1.250, g3k-1926:original/1.232
- `g3k-1089` (geometry3k) Solve for x.
  - top3: g3k-1441:original/1.272, g3k-768:original/1.270, g3k-2013:original/1.267
- `g3k-1092` (geometry3k) Find x to the nearest tenth. Assume that segments that appear to be tangent are tangent.
  - top3: g3k-201:original/1.290
- `g3k-1094` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-2231:original/1.287
- `g3k-1115` (geometry3k) Find the area of the quadrilateral.
  - top3: g3k-1107:original/1.281, g3k-989:original/1.281, g3k-283:original/1.276
- `g3k-1122` (geometry3k) Find the measure of the altitude drawn to the hypotenuse.
  - top3: g3k-2035:original/1.286
- `g3k-1135` (geometry3k) Find z in the figure.
  - top3: g3k-787:original/1.274, g3k-684:original/1.252
- `g3k-1142` (geometry3k) Find y.
  - top3: g3k-111:original/1.248, g3k-1105:original/1.248, g3k-1326:original/1.246
- `g3k-1143` (geometry3k) Find the area of the figure. Round to the nearest tenth if necessary.
  - top3: g3k-387:original/1.288, g3k-2173:original/1.286, g3k-1513:original/1.283
- `g3k-1151` (geometry3k) Find y.
  - top3: g3k-111:original/1.248, g3k-1105:original/1.248, g3k-1326:original/1.246

**另标其他原题（最多 15 条）**

- `g3k-1005` (geometry3k) Find m \angle S.
  - top3: g3k-1566:original/1.258, g3k-1005:original/1.251, g3k-2575:original/1.250
- `g3k-1006` (geometry3k) Find x.
  - top3: g3k-1829:original/1.247, g3k-793:original/1.245, g3k-2957:original/1.245
- `g3k-102` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-2231:original/1.287
- `g3k-1028` (geometry3k) Find R S.
  - top3: g3k-2216:original/1.254
- `g3k-1040` (geometry3k) Find m \angle R.
  - top3: g3k-481:original/1.259, g3k-2489:original/1.249, g3k-2123:original/1.247
- `g3k-1041` (geometry3k) Find m \angle K.
  - top3: g3k-1366:original/1.266, g3k-930:original/1.264, g3k-1041:original/1.254
- `g3k-1050` (geometry3k) Find x.
  - top3: g3k-1829:original/1.247, g3k-793:original/1.245, g3k-2957:original/1.245
- `g3k-1069` (geometry3k) Find m \angle Q.
  - top3: g3k-756:original/1.260, g3k-1069:original/1.243
- `g3k-1075` (geometry3k) Find A B.
  - top3: g3k-313:original/1.253, g3k-2956:original/1.250, g3k-1926:original/1.232
- `g3k-1089` (geometry3k) Solve for x.
  - top3: g3k-1441:original/1.272, g3k-768:original/1.270, g3k-2013:original/1.267
- `g3k-1092` (geometry3k) Find x to the nearest tenth. Assume that segments that appear to be tangent are tangent.
  - top3: g3k-201:original/1.290
- `g3k-1094` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-2231:original/1.287
- `g3k-1115` (geometry3k) Find the area of the quadrilateral.
  - top3: g3k-1107:original/1.281, g3k-989:original/1.281, g3k-283:original/1.276
- `g3k-1122` (geometry3k) Find the measure of the altitude drawn to the hypotenuse.
  - top3: g3k-2035:original/1.286
- `g3k-1130` (geometry3k) In rhombus L M P Q, m \angle Q L M = 2 x^ { 2 } - 10, m \angle Q P M = 8 x, and M P = 10. Find m \angle L P Q.
  - top3: g3k-1130:original/1.285, g3k-1936:original/1.280

### 渲染图

| 分组 | 样本 | 命中@3 | 首位 | 标成原题 | 误标其他原题 | 空结果 | 均返回 | 均耗时s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 797 | 41.0% | 40.3% | 40.5% | 17.6% | 50.9% | 0.72 | 0.85 |
| geometry | 797 | 41.0% | 40.3% | 40.5% | 17.6% | 50.9% | 0.72 | 0.85 |

### 图搜失败样例

未命中 470，命中但非首位 6，命中但未标原题 4，另标其他原题 140。

**未命中（最多 15 条）**

- `g3k-1005` (geometry3k) Find m ∠ S.(2x+5)°(2x+7)°
  - top3: （空）
- `g3k-1006` (geometry3k) Find x.2x+13x-1
  - top3: （空）
- `g3k-102` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.148°
  - top3: （空）
- `g3k-1028` (geometry3k) Find R S.3x + 22x+4
  - top3: （空）
- `g3k-1040` (geometry3k) Find m ∠ R.27. M
  - top3: （空）
- `g3k-1041` (geometry3k) Find m ∠ K.(2x − 8)°(3x−6)°(x+ 10)°
  - top3: （空）
- `g3k-1045` (geometry3k) In the figure, Q R ∥ T S, Q T∥ R S, and m ∠ 1 = 131. Find the measure of ∠ 6.
  - top3: （空）
- `g3k-1050` (geometry3k) Find x.
  - top3: g3k-1829:original/1.253, g3k-1377:original/1.249
- `g3k-1069` (geometry3k) Find m ∠Q.27. M
  - top3: （空）
- `g3k-1075` (geometry3k) Find A B.
  - top3: （空）
- `g3k-1082` (geometry3k) G J is a diameter of K. Find m G L H.122°
  - top3: （空）
- `g3k-1089` (geometry3k) Solve for x.4.5 m(4x +1)°(5x−5)°4.5 m
  - top3: （空）
- `g3k-1096` (geometry3k) Find the area of a regular hexagon with a perimeter of 72 feet.12 ft12 ft←12 ft→
  - top3: （空）
- `g3k-110` (geometry3k) P M is a diameter of R. Find m M Q.115°
  - top3: （空）
- `g3k-1103` (geometry3k) The pair of polygons is similar. Find A B.
  - top3: （空）

**命中但未标原题（最多 15 条）**

- `g3k-128` (geometry3k) According to the Perpendicular Bisector Theorem, what is the length of segment A B below?2.5 cm
  - top3: g3k-128:variant/0.765
- `g3k-2521` (geometry3k) Find x for the equilateral triangle R S T if R S = x + 9, S T = 2 x, and R T = 3 x - 9.3x-9
  - top3: g3k-2521:variant/0.793
- `g3k-282` (geometry3k) The height of a triangle is 5 centimeters more than its base. The area of the triangle is 52 square centimeters. Findthe
  - top3: g3k-282:variant/0.786
- `g3k-634` (geometry3k) Find the measure of R S of equilateral triangle R S T if R S = x + 9, S T = 2 x, and R T = 3 x - 9.3x-9
  - top3: g3k-634:variant/0.772

**另标其他原题（最多 15 条）**

- `g3k-1050` (geometry3k) Find x.
  - top3: g3k-1829:original/1.253, g3k-1377:original/1.249
- `g3k-1053` (geometry3k) In P, m E N = 66 and m G P M = 89. Find m G M E.
  - top3: g3k-1053:original/1.291, g3k-1104:original/1.281
- `g3k-1058` (geometry3k) Find the variable of d to the nearest tenth. Assume that segments that appear to be tangent are tangent.
  - top3: g3k-1058:original/1.296, g3k-699:original/1.282
- `g3k-1094` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-1094:original/1.292, g3k-148:original/1.279, g3k-187:original/1.270
- `g3k-1104` (geometry3k) In P, m E N = 66 and m G P M = 89. Find m E G N.
  - top3: g3k-1104:original/1.290, g3k-454:original/1.284
- `g3k-1130` (geometry3k) In rhombus L M P Q, m Q L M = 2 x^ 2 - 10, m Q P M = 8 x, and M P = 10. Find m L
  - top3: g3k-1130:original/1.291, g3k-1936:original/1.287
- `g3k-1151` (geometry3k) Find y.
  - top3: g3k-1303:original/1.251
- `g3k-1158` (geometry3k) Find y.
  - top3: g3k-1158:original/1.257, g3k-805:original/1.254, g3k-1649:original/1.251
- `g3k-1167` (geometry3k) Find x.
  - top3: g3k-1167:original/1.251, g3k-1556:original/1.249, g3k-1372:original/1.248
- `g3k-1211` (geometry3k) Find the area of the shaded sector. Round to the nearest tenth.
  - top3: g3k-1211:original/1.291, g3k-846:original/1.278, g3k-187:original/1.270
- `g3k-1237` (geometry3k) In △ A B C, B D is a median. If A D = 3 x + 5 and C D = 5 x - 1, find A C.
  - top3: g3k-535:original/1.290
- `g3k-1260` (geometry3k) Find x.
  - top3: g3k-1260:original/1.252, g3k-2234:original/1.251
- `g3k-1291` (geometry3k) Find x.
  - top3: g3k-1669:original/1.250
- `g3k-1308` (geometry3k) Find x.
  - top3: g3k-2482:original/1.252
- `g3k-1315` (geometry3k) Find the variable of x to the nearest tenth. Assume that segments that appear to be tangent are tangent.
  - top3: g3k-1315:original/1.296, g3k-699:original/1.283
