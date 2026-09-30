"""소재 찾기 (finder) tab — find high-performing overseas shorts to dub into Japanese.

Self-contained feature package: its own SQLite DB (data/finder.db), YouTube Data
API client, search/metrics/filters, and an APIRouter mounted at /api/finder. It
does NOT touch the existing dubbing pipeline or its JSON job store — the only
shared code is backend.common.llm (Anthropic client) and, for the "작업하기"
download, backend.pipeline.download.
"""
