from pathlib import Path

from PIL import Image

from eqsearch.config import SearchConfig
from eqsearch.index.gallery import Gallery
from eqsearch.pipeline.search import search
from eqsearch.vision.ocr import get_ocr_backend

gallery = Gallery.load(Path("data/index"), SearchConfig())
ocr = get_ocr_backend("auto")
folder = Path("data/sample_queries/math")
for path in sorted(folder.glob("*.png")):
    img = Image.open(path).convert("RGB")
    resp = search(gallery, text="", image=img, ocr=ocr)
    hits = [(c.item.id, c.relation, round(c.final_score, 3)) for c in resp.results]
    query = (resp.query_text or "").replace("\n", " ")[:140]
    print("===", path.name)
    print(" query=", query)
    print(" originals=", resp.originals, "hits=", hits or "NONE")
