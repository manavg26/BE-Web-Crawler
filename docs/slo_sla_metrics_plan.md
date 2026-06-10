# SLO/SLA and Success Metrics Plan

This document explains the crawler SLOs, SLAs, success metrics, what the current PoC can measure, and which database tables should be added for production-grade observability.

## Purpose

The PoC currently stores crawl jobs, final crawl records, and local broker messages. This is enough for basic operational visibility, but not enough for the full SLO/SLA reporting expected in a production billion-URL crawler.

In production, metrics should be emitted to Prometheus/OpenTelemetry and also persisted where historical analysis is useful. The database tables below are planned additions for durable reporting, debugging, and post-run audits.

## Planned SLOs

| Area | SLO | How It Is Measured |
|---|---:|---|
| Crawl throughput | >= 1,650 URLs/sec sustained | completed crawl jobs per second over a batch window |
| Full batch completion | <= 7 days for 1B URLs | batch completed_at - batch submitted_at |
| Crawl success rate | >= 92% of reachable URLs | successful fetches / total attempted fetches |
| Parse success rate | >= 99.5% of fetched pages | successful parses / fetched pages |
| Metadata freshness | <= 4 hours after fetch | result persisted_at - fetch_completed_at |
| Serving API availability | >= 99.9% | successful API requests / total API requests |
| Serving API p99 latency | <= 50 ms | p99 duration_ms from API request logs |
| Queue processing lag | no sustained growth > 15 minutes | pending/in_progress broker messages by topic |
| Cost per million pages | within agreed forecast | cloud billing labels + processed URL count |

## SLA Candidates

SLAs should be slightly looser than internal SLOs to preserve operational error budget.

| External SLA | Candidate Target |
|---|---:|
| Metadata API availability | 99.9% monthly |
| Metadata API p99 latency | <= 100 ms |
| Monthly batch availability | completed within 8 days |
| Data freshness after fetch | <= 6 hours |

## Success Metrics

### Crawl Quality

| Metric | Target |
|---|---:|
| Crawl success rate | >= 92% for reachable URLs |
| Non-2xx classification accuracy | 100% not parsed as page content |
| Robots.txt compliance | 100% |
| Retry exhaustion visibility | 100% failed jobs have final error reason |

### Extraction Quality

| Metric | Target |
|---|---:|
| Title extraction accuracy | >= 95% on golden set |
| Meta description extraction accuracy | >= 90% on golden set |
| Body extraction quality | >= 90% acceptable on golden set |
| Structured data recall | >= 90% for JSON-LD pages |

### Classification Quality

| Metric | Target |
|---|---:|
| Page type accuracy | >= 90% on golden set |
| Topic precision@3 | >= 70% on golden set |
| Topic confidence distribution | no sudden p50/p95 drift between runs |

### Pipeline Quality

| Metric | Target |
|---|---:|
| Dead-letter queue depth | below alert threshold |
| Duplicate job rate | below expected duplicate baseline |
| Parser failure rate | < 0.5% |
| Retryable fetch failure rate | monitored by domain/status |

## What The Current PoC Can Measure

The current PoC can calculate basic metrics from existing tables.

### From `crawl_jobs`

Available fields:

```text
job_id
url
status
record_json
error
created_at
updated_at
```

Possible metrics:

```text
jobs by status
completed jobs count
failed jobs count
basic completion time: updated_at - created_at
HTTP status distribution from record_json.http_status
fetch duration from record_json.fetch_duration_ms
page type distribution from record_json.page_type
warning/error counts from record_json
word count distribution from record_json.word_count
topic confidence distribution from record_json.topic_confidence
```

### From `broker_messages`

Available fields:

```text
message_id
topic
message_key
payload_json
status
created_at
claimed_at
acked_at
```

Possible metrics:

```text
messages by topic and status
pending backlog by topic
in-progress message count
acked message count
basic topic processing latency: acked_at - created_at
basic claim latency: claimed_at - created_at
```

## Current Gaps

The PoC does not yet explicitly track:

```text
batch_id
domain
worker_id
fetch attempt number
fetch retry history
per-stage start/end timestamps
parse duration
schema validation failures
dead-letter messages
API request latency
serving API availability
queue partition lag
cost data
raw HTML byte size
compressed HTML storage path
```

These gaps are acceptable for the PoC but should be closed before production.

## Planned Tables

### `crawl_batches`

Purpose: track batch-level SLOs such as full batch completion time.

```sql
CREATE TABLE crawl_batches (
  batch_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  total_urls INTEGER NOT NULL,
  submitted_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  created_by TEXT,
  notes TEXT
);
```

Supports:

```text
full batch completion SLO
throughput per batch
batch-level failure rate
cost per batch when joined with billing metadata
```

### `crawl_attempts`

Purpose: track every fetch attempt, including retries.

```sql
CREATE TABLE crawl_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  batch_id TEXT,
  url TEXT NOT NULL,
  domain TEXT NOT NULL,
  attempt_number INTEGER NOT NULL,
  http_status INTEGER,
  retryable BOOLEAN NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  duration_ms INTEGER,
  error TEXT,
  warning TEXT,
  worker_id TEXT
);

CREATE INDEX idx_crawl_attempts_job_id ON crawl_attempts(job_id);
CREATE INDEX idx_crawl_attempts_domain ON crawl_attempts(domain);
CREATE INDEX idx_crawl_attempts_status ON crawl_attempts(http_status);
CREATE INDEX idx_crawl_attempts_started_at ON crawl_attempts(started_at);
```

Supports:

```text
crawl success rate
retry rate
HTTP status distribution
domain-level block detection
fetch latency percentiles
worker-level debugging
```

### `parse_attempts`

Purpose: track parse and classification quality.

```sql
CREATE TABLE parse_attempts (
  attempt_id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL,
  batch_id TEXT,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  duration_ms INTEGER,
  success BOOLEAN NOT NULL,
  page_type TEXT,
  word_count INTEGER,
  structured_data_types_count INTEGER,
  topic_confidence DOUBLE PRECISION,
  schema_version INTEGER NOT NULL,
  error TEXT,
  worker_id TEXT
);

CREATE INDEX idx_parse_attempts_job_id ON parse_attempts(job_id);
CREATE INDEX idx_parse_attempts_success ON parse_attempts(success);
CREATE INDEX idx_parse_attempts_page_type ON parse_attempts(page_type);
```

Supports:

```text
parse success rate
parse latency percentiles
page type distribution
topic confidence p50/p95
schema validation failure tracking
body extraction quality monitoring
```

### `api_request_logs`

Purpose: support serving API SLA and latency reporting.

```sql
CREATE TABLE api_request_logs (
  request_id TEXT PRIMARY KEY,
  method TEXT NOT NULL,
  path TEXT NOT NULL,
  status_code INTEGER NOT NULL,
  duration_ms INTEGER NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  error TEXT
);

CREATE INDEX idx_api_request_logs_created_at ON api_request_logs(created_at);
CREATE INDEX idx_api_request_logs_path ON api_request_logs(path);
CREATE INDEX idx_api_request_logs_status_code ON api_request_logs(status_code);
```

Supports:

```text
API availability SLA
API p50/p95/p99 latency
API error rate
endpoint-level debugging
```

### `dead_letter_messages`

Purpose: preserve failed messages for replay and investigation.

```sql
CREATE TABLE dead_letter_messages (
  dlq_id TEXT PRIMARY KEY,
  original_message_id TEXT,
  job_id TEXT,
  topic TEXT NOT NULL,
  payload_json JSONB NOT NULL,
  error TEXT NOT NULL,
  retry_count INTEGER NOT NULL,
  failed_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_dead_letter_messages_topic ON dead_letter_messages(topic);
CREATE INDEX idx_dead_letter_messages_job_id ON dead_letter_messages(job_id);
CREATE INDEX idx_dead_letter_messages_failed_at ON dead_letter_messages(failed_at);
```

Supports:

```text
DLQ depth
failure reason distribution
safe replay
debugging systematic worker failures
```

### `domain_crawl_policies`

Purpose: store per-domain crawl controls.

```sql
CREATE TABLE domain_crawl_policies (
  domain TEXT PRIMARY KEY,
  crawl_delay_ms INTEGER NOT NULL DEFAULT 1000,
  max_concurrency INTEGER NOT NULL DEFAULT 1,
  respect_robots BOOLEAN NOT NULL DEFAULT TRUE,
  requires_rendering BOOLEAN NOT NULL DEFAULT FALSE,
  blocked_until TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL
);
```

Supports:

```text
domain politeness
per-domain throttling
circuit breaker behavior
selective headless rendering
```

### `data_quality_checks`

Purpose: store post-run quality validation results.

```sql
CREATE TABLE data_quality_checks (
  check_id TEXT PRIMARY KEY,
  batch_id TEXT,
  check_name TEXT NOT NULL,
  status TEXT NOT NULL,
  measured_value DOUBLE PRECISION,
  threshold_value DOUBLE PRECISION,
  details_json JSONB,
  created_at TIMESTAMPTZ NOT NULL
);
```

Supports:

```text
schema validation tracking
quality gates before release
golden-set comparison results
regression detection
```

### `cost_metrics`

Purpose: connect processed volume to cloud cost.

```sql
CREATE TABLE cost_metrics (
  metric_id TEXT PRIMARY KEY,
  batch_id TEXT,
  service_name TEXT NOT NULL,
  cost_usd DOUBLE PRECISION NOT NULL,
  pages_processed INTEGER,
  bytes_processed BIGINT,
  measured_at TIMESTAMPTZ NOT NULL
);
```

Supports:

```text
cost per million pages
service-level cost breakdown
budget alerts
capacity planning
```

## Suggested Additions To Existing `crawl_jobs`

The current `crawl_jobs` table can be expanded with:

```sql
ALTER TABLE crawl_jobs ADD COLUMN batch_id TEXT;
ALTER TABLE crawl_jobs ADD COLUMN domain TEXT;
ALTER TABLE crawl_jobs ADD COLUMN submitted_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN fetch_started_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN fetch_completed_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN parse_started_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN parse_completed_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN completed_at TIMESTAMPTZ;
ALTER TABLE crawl_jobs ADD COLUMN retry_count INTEGER DEFAULT 0;
```

These columns make per-job stage timing easier without parsing logs or joining message tables.

## Example Queries

### Jobs By Status

```sql
SELECT status, COUNT(*)
FROM crawl_jobs
GROUP BY status;
```

### Basic Queue Backlog

```sql
SELECT topic, status, COUNT(*)
FROM broker_messages
GROUP BY topic, status
ORDER BY topic, status;
```

### Fetch Success Rate

```sql
SELECT
  SUM(CASE WHEN http_status BETWEEN 200 AND 299 THEN 1 ELSE 0 END)::float
  / COUNT(*) AS fetch_success_rate
FROM crawl_attempts
WHERE completed_at IS NOT NULL;
```

### Parse Success Rate

```sql
SELECT
  SUM(CASE WHEN success THEN 1 ELSE 0 END)::float
  / COUNT(*) AS parse_success_rate
FROM parse_attempts;
```

### API p99 Latency

```sql
SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99_ms
FROM api_request_logs
WHERE created_at >= NOW() - INTERVAL '1 hour';
```

### Dead-Letter Queue Depth

```sql
SELECT topic, COUNT(*) AS dlq_depth
FROM dead_letter_messages
GROUP BY topic;
```

## Production Recommendation

For production, do not rely only on the OLTP database for SLOs. Use:

```text
Prometheus / Cloud Monitoring for live metrics and alerts
OpenTelemetry for traces across API -> queue -> fetch -> parse -> store
PostgreSQL/warehouse tables for historical audits and reporting
Grafana dashboards for SLO review
PagerDuty/OpsGenie alerts for SLO burn-rate alerts
```

The database tables above are still useful because they provide durable forensic detail when debugging failed crawls, blocked domains, parse regressions, or batch-level delays.
