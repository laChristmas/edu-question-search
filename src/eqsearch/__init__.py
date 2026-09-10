"""变式题检索：原题优先，然后变式，最多 3 条。"""

from eqsearch.config import SearchConfig
from eqsearch.models import GalleryItem, SearchResponse
from eqsearch.pipeline.ingest import ingest_ape, ingest_records
from eqsearch.pipeline.search import search

__all__ = [
    "SearchConfig",
    "GalleryItem",
    "SearchResponse",
    "ingest_ape",
    "ingest_records",
    "search",
]
