# PoC Decisions and Production Improvements

This document explains the deliberate differences between the proof of concept and the production-scale design.

## Database Decision

### Chosen PoC Direction

Use a single database layer for the PoC.

The target production-like choice is PostgreSQL, because the PoC needs:

- durable crawl job state
- lookup by job id
- lookup by URL
- structured JSON result storage
- simple local reasoning during an interview
- room to add status transitions, retries, timestamps, and error tracking

The current code uses SQLite as a zero-infrastructure local stand-in for PostgreSQL. This keeps the demo runnable without asking the reviewer to install or run a database server. The schema maps cleanly to PostgreSQL:

```sql
CREATE TABLE crawl_jobs (
  job_id TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  status TEXT NOT NULL,
  record_json JSONB,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_crawl_jobs_url ON crawl_jobs(url);
CREATE INDEX idx_crawl_jobs_status ON crawl_jobs(status);
```

### Why PostgreSQL Over Elasticsearch for the PoC?

PostgreSQL is the better single database for this stage.

| Criterion | PostgreSQL | Elasticsearch |
|---|---|---|
| Job state tracking | Strong fit | Possible, but not ideal |
| Exact lookup by job id | Strong fit | Good |
| Transactional updates | Strong fit | Weaker |
| JSON crawl record storage | Strong fit with JSONB | Strong fit |
| Full-text search | Good enough for PoC | Excellent |
| Operational simplicity | Simple | More moving parts |
| Best use case | System of record | Search/index layer |

Elasticsearch becomes attractive when the product needs search-heavy use cases, such as finding pages by topic, body text, product phrase, brand, or content similarity. For this PoC, we mostly need durable job/result retrieval, not search analytics.

### Why Not Multiple Databases in the PoC?

Multiple stores are correct for production, but too much operational surface area for a home-assignment demo. A three-store PoC would require object storage, warehouse setup, and a serving index before the core crawler can even be reviewed.

The single database keeps the PoC focused while preserving the right interfaces:

```text
POST /crawl
  -> store job
  -> crawl.fetch topic
  -> crawl.parse topic
  -> store structured result
  -> GET /crawl/{job_id}
```

## Fetch and Parse Layer Decision

### Current PoC Shape

The PoC now separates fetch and parse operationally with Kafka-like local topics:

```text
API request
  -> create crawl job in DB
  -> publish message to crawl.fetch topic
  -> fetch worker downloads HTML
  -> publish fetched HTML message to crawl.parse topic
  -> parse worker extracts metadata/body/topics
  -> save final CrawlRecord in DB
  -> caller retrieves by job id
```

This mirrors the production design more closely than doing everything in a single request.

### PoC Limitation

The broker is a SQLite-backed local stand-in, not an actual Kafka/Redpanda cluster. This is fine for a demo but not enough for production because:

- consumer groups and partition assignment are simplified
- fetch and parse cannot scale independently across machines
- replay and retention are much weaker than Kafka/Redpanda
- there is no domain-partitioned scheduling
- raw HTML is persisted only as a local broker payload, not as compressed object storage

## Planned Production Improvements

### 1. Replace In-Memory Queues with Durable Queues

PoC:

```text
SQLite-backed local topics: crawl.fetch and crawl.parse
```

Production:

```text
Redpanda / Kafka / Pub/Sub / SQS
```

Reason:

- durable replay
- independent worker scaling
- backpressure
- dead-letter queues
- partitioning by registered domain for politeness

### 2. Split Fetch and Parse into Separate Services

PoC:

```text
same FastAPI process
```

Production:

```text
API service
Go fetch workers
Python parse/classify workers
```

Reason:

- fetch is I/O-bound and benefits from Go's concurrency and memory profile
- parsing/classification benefits from Python libraries
- each tier can autoscale independently

### 3. Add Multiple Storage Systems

PoC:

```text
single DB for job + crawl record
```

Production:

```text
GCS/S3                 -> compressed raw HTML
BigQuery/ClickHouse    -> analytical metadata warehouse
Bigtable/DynamoDB/OpenSearch -> serving index
```

Reason:

- raw HTML enables parser reprocessing without re-crawling
- warehouse enables large analytical scans
- serving index enables low-latency API reads

### 4. Store Raw HTML Separately

PoC:

```text
raw HTML is not persisted
```

Production:

```text
{year_month}/{domain_hash}/{url_sha256}.html.gz
```

Reason:

- parser bugs can be fixed by replaying raw HTML
- schema changes can be backfilled
- avoids paying network cost again

### 5. Add Politeness and Domain Scheduling

PoC:

```text
robots.txt check per request
```

Production:

```text
domain-partitioned queue
Redis token bucket
robots.txt cache
per-domain circuit breaker
```

Reason:

- prevents hammering domains
- reduces bans
- handles domain-specific crawl delays

### 6. Add Deduplication

PoC:

```text
no dedup beyond querying stored jobs
```

Production:

```text
Bloom filter for input URL dedup
SimHash for content dedup
```

Reason:

- reduces queue size
- reduces storage
- reduces parse/classification cost

### 7. Add Headless Rendering Tier

PoC:

```text
static HTML fetch only
```

Production:

```text
Playwright rendering queue for selected pages/domains
```

Reason:

- handles JS-heavy sites
- keeps expensive rendering selective instead of default

### 8. Add Observability and Recovery

PoC:

```text
status stored in DB
```

Production:

```text
metrics, traces, logs, DLQ, retries, runbooks, SLO alerts
```

Reason:

- find bottlenecks
- recover failed batches
- measure success rates and cost per page

## Interview Summary

The PoC intentionally uses a single database and in-process workers to stay runnable, but the shape matches production:

```text
API -> job store -> crawl.fetch topic -> fetch worker -> crawl.parse topic -> parse worker -> result store -> retrieval API
```

The production version replaces each local simplification with a durable/scalable equivalent:

```text
SQLite/PostgreSQL-style store -> PostgreSQL plus warehouse/index stores
SQLite-backed local topics -> Redpanda/Kafka/Pub/Sub
in-process workers -> autoscaled fetch/parse services
in-memory HTML handoff -> object storage raw HTML
basic status -> full observability and retry/DLQ controls
```
