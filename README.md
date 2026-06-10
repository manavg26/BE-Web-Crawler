# BrightEdge Web Crawler Assignment

Working proof-of-concept crawler for the BrightEdge scale home assignment.

The service exposes a small FastAPI API that accepts crawl jobs, publishes them to a Kafka-like local topic, fetches URLs through a single async fetch worker, publishes fetched HTML to a parse topic, parses/classifies through a single parse worker, persists the result in a single local database, and returns a unified JSON crawl record by job id. The implementation is intentionally demo-friendly while the system design plan covers the billion-URL production architecture.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn crawler.main:app --reload
```

On machines where `python3` points to a very new interpreter without package wheels, use Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

```bash
curl "http://127.0.0.1:8000/health"
curl -X POST "http://127.0.0.1:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://blog.rei.com/camp/how-to-introduce-your-indoorsy-friend-to-the-outdoors/"}'
```

## API

### `GET /health`

Returns service status.

### `POST /crawl`

Queues a crawl job and returns immediately.

Request:

```json
{
  "url": "https://example.com/article"
}
```

Response:

```json
{
  "job_id": "9f8d...",
  "status": "queued",
  "result_url": "/crawl/9f8d..."
}
```

### `GET /crawl/{job_id}`

Returns the stored job status and the extracted record once parsing is complete.

### `GET /crawl?url=...`

Backward-compatible direct crawl endpoint. It fetches, parses, and returns the crawl record in one request. The production-like flow is `POST /crawl` followed by `GET /crawl/{job_id}`.

## Output Schema

Every page type returns the same schema. Product, article, news, category, homepage, and other pages all share nullable fields plus an extensible `structured_data` object.

```json
{
  "url": "https://...",
  "final_url": "https://...",
  "http_status": 200,
  "fetched_at": "2026-06-10T00:00:00Z",
  "fetch_duration_ms": 412,
  "page_type": "article",
  "language": "en",
  "canonical": "https://...",
  "title": "...",
  "meta_description": "...",
  "meta_keywords": ["..."],
  "og_title": "...",
  "og_description": "...",
  "og_image": "...",
  "headings": {
    "h1": ["..."],
    "h2": ["..."],
    "h3": ["..."]
  },
  "body_text": "...",
  "word_count": 1240,
  "structured_data": {
    "types": ["Article"],
    "json_ld": []
  },
  "topics": [
    {"label": "search engine optimization", "score": 0.88}
  ],
  "primary_category": "search engine optimization",
  "topic_confidence": 0.88,
  "errors": [],
  "warnings": []
}
```

## Design Choices

- `httpx` async fetcher with timeouts, retries, redirects, user-agent, and robots.txt checks.
- Retry only for transient statuses: `408`, `409`, `425`, `429`, `500`, `502`, `503`, `504`.
- Non-2xx responses are recorded but not parsed as content.
- Structured JSON logging is configured at app startup and decorator-based logging wraps key API/fetch/parse operations.
- SQLite-backed Kafka-like topics: `crawl.fetch` and `crawl.parse`.
- One fetch worker and one parse worker to mirror separate production services without adding local infrastructure.
- Single local SQLite database for the PoC, used as a zero-infrastructure stand-in for PostgreSQL.
- `selectolax` parser when available for fast metadata extraction.
- `trafilatura` when available for main-body extraction.
- Pydantic v2 schema validation for consistent downstream records.
- Lightweight local topic extraction for the demo; production can replace this with KeyBERT or a batch inference service without changing the response schema.
- Honest anti-bot handling: blocked or thin pages are reported with warnings rather than bypassed.

## Test URLs

```bash
curl -X POST "http://127.0.0.1:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://blog.rei.com/camp/how-to-introduce-your-indoorsy-friend-to-the-outdoors/"}'
curl "http://127.0.0.1:8000/crawl/<job_id-from-response>"

curl -X POST "http://127.0.0.1:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.cnn.com/2025/01/01/tech/example"}'
curl "http://127.0.0.1:8000/crawl/<job_id-from-response>"

curl -X POST "http://127.0.0.1:8000/crawl" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.amazon.com/dp/B08N5WRWNW"}'
curl "http://127.0.0.1:8000/crawl/<job_id-from-response>"
```

Amazon and similar sites may return `403`, `429`, `503`, CAPTCHA, or very thin HTML to a normal server-side crawler. The service records the status and emits warnings such as `blocked_by_anti_bot` or `thin_content`.

For non-2xx responses, the crawler stores the HTTP status and warnings but does not parse the response HTML. This prevents access-denied, CAPTCHA, or CDN challenge pages from being mistaken for the target page content.

## Docker

```bash
docker build -t brightedge-crawler .
docker run --rm -p 8080:8080 brightedge-crawler
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Production Scale Summary

For a billion-URL system, this crawler should become the parse/classify worker behind a distributed pipeline:

1. Ingest monthly URL dump.
2. Normalize and deduplicate URLs with a Bloom filter.
3. Publish to Kafka or Pub/Sub partitioned by registered domain.
4. Fetch workers enforce robots.txt, per-domain token buckets, retry, and circuit breakers.
5. Raw HTML is compressed into object storage.
6. Parse/classify workers emit validated records.
7. Store outputs in object storage, warehouse, and serving index separately.

PoC tradeoffs and planned production improvements are in `docs/poc_to_production.md`.
Planned SLO/SLA metrics and future observability tables are in `docs/slo_sla_metrics_plan.md`.


## AI Usage Declaration

AI assistance was used to structure the design, identify crawler edge cases, and generate/refine code. All generated code was reviewed, scoped to the assignment, and verified with tests.
