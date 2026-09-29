"""
Guidance Discovery — operational configuration: every tuning static, named in one place.

`filters.py` holds *what* we pull (scope — the organisations and document types).
This file holds *how* we pull it (endpoints, page size, rate limits, paths). No
magic numbers should appear in the stage scripts; they all live here with a name.
"""

# ── Stage 1: discovery (GOV.UK Search API) ──────────────────────────────────
SEARCH_API_URL = "https://www.gov.uk/api/search.json"
# Search API drops withdrawn pages unless this debug flag is set. Content
# audits want those pages: they are still on GOV.UK, just unlisted from search.
SEARCH_DEBUG = "include_withdrawn"
SEARCH_FIELDS = (
    "title,link,description,content_id,view_count,"
    "content_store_document_type,public_timestamp,"
    "organisations,primary_publishing_organisation,is_withdrawn"
)
PAGE_SIZE = 1000  # Search API max results per request; also the pagination step.

# ── Stage 2: body fetch (GOV.UK Content API) ────────────────────────────────
CONTENT_API_BASE = "https://www.gov.uk"  # page url path is appended as /api/content{path}
DEFAULT_CONCURRENCY = 3                   # simultaneous in-flight requests
DEFAULT_RATE = 10.0                       # requests per second (token-bucket limiter)
REQUEST_TIMEOUT = 30.0                    # seconds, per httpx request
MAX_RETRIES = 5                           # attempts on HTTP 429 before giving up
INITIAL_BACKOFF = 5.0                     # seconds, first 429 wait
MAX_BACKOFF = 60.0                        # seconds, backoff ceiling
PROGRESS_EVERY = 50                       # log a progress line every N pages

# ── Default file locations (the inter-stage hand-off / restart cache) ───────
DEFAULT_SEARCH_OUTPUT = "output/search_api.json"  # stage 1 writes, stage 2 reads
DEFAULT_BODY_OUTPUT = "output/with_body.json"     # stage 2 writes, Guidance Relevance Filter reads
