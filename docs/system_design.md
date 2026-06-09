# Billion-URL Web Crawler System Design

This document summarizes the execution plan and production design for the BrightEdge crawler assignment. The local FastAPI service is the proof of concept; this design describes how it becomes a reliable billion-URL platform.

## Assignment Strategy

The crawler demonstrates extraction quality and schema shape. The main engineering evaluation is the scale plan: reliability, storage design, throughput, cost, monitoring, blockers, and release sequencing.

The proof of concept uses Python because it is fast to ship and has strong parsing and extraction libraries. At production scale, fetching and parsing should be split: Go fetch workers for high-concurrency network I/O, Python parse/classify workers for HTML extraction and model ecosystem.

## Proof-of-Concept Scope

The demo service exposes:

- `GET /health`
- `POST /crawl`
- `GET /crawl?url=...`

Each crawl result includes:

- HTTP status, final URL, fetch timing, and fetch timestamp
- title, canonical, meta description, meta keywords, Open Graph fields
- h1/h2/h3 headings
- extracted body text and word count
- JSON-LD structured data and schema.org types
- page type classification
- topics and confidence
- errors and warnings

The crawler reports anti-bot or thin-content cases honestly. For example, Amazon may return `403`, `429`, `503`, CAPTCHA, or very little HTML to a normal server-side crawler. The demo records that outcome instead of attempting ToS-sensitive bypasses.

## Production Architecture

```text
Monthly URL dump
  -> URL normalizer
  -> Bloom filter input dedup
  -> domain-partitioned Kafka/Pub/Sub queue
  -> Go fetch workers
  -> compressed raw HTML object store
  -> Python parse/classify workers
  -> warehouse + serving index + dead-letter queues
```

## Key Design Decisions

### Three Stores

Use separate stores for separate workloads:

- Object storage for compressed raw HTML and headers.
- Columnar warehouse such as BigQuery or ClickHouse for analytics.
- Serving index such as Bigtable, DynamoDB, or OpenSearch for low-latency API reads.

This adds write complexity, but avoids forcing one database to handle cold archive, analytical scans, and p99 serving reads.

### Raw HTML Retention

Store compressed raw HTML before parsing. If a parser bug or schema change is discovered, re-run parse workers from object storage instead of re-crawling a billion pages.

Object key pattern:

```text
{year_month}/{domain_hash}/{url_sha256}.html.gz
```

### Domain-Partitioned Queue

Partition queue messages by registered domain. Workers enforce per-domain token buckets and robots.txt rules. This prevents a large batch from hammering popular domains.

### Selective JavaScript Rendering

Static fetch first. Send pages to a Playwright rendering tier only when the static body is too thin, structured data is missing, or the domain is known to require rendering. Headless rendering is much more expensive and should not be the default.

### Deduplication

Use two stages:

- Input dedup with a Bloom filter.
- Content dedup with SimHash after body extraction.

This saves queue capacity, storage, and downstream classification cost.

## Scale Assumptions

| Parameter | Assumption |
|---|---:|
| Monthly URL volume | 1B URLs |
| Average HTML size | 100 KB |
| Average metadata size | 2 KB |
| Average extracted body | 10 KB |
| Distinct domains | 10M |
| Sustained throughput target | 1,650 URLs/sec |
| Batch completion SLO | 7 days |

## SLOs

| Metric | Target |
|---|---:|
| Crawl throughput | >= 1,650 URLs/sec sustained |
| Full batch completion | <= 7 days |
| Crawl success rate | >= 92% of reachable URLs |
| Parse success rate | >= 99.5% |
| Warehouse freshness | <= 4 hours after fetch |
| Serving API availability | >= 99.9% |
| Serving API p99 latency | <= 50 ms |

## Monitoring

Track:

- queue lag by partition
- fetch success and error rates by status code
- `403`, `429`, and `503` spikes by domain
- robots.txt disallow counts
- per-domain throttle events
- dead-letter queue depth
- parse failure rate
- average body word count
- topic confidence distribution
- schema validation failures
- object-store bytes written
- warehouse rows inserted
- serving API latency and error rate

Use structured JSON logs, OpenTelemetry traces, metrics dashboards, and alerting tied to SLOs.

## Self-Healing

- Retry with exponential backoff.
- Per-domain circuit breakers.
- Dead-letter queues for permanent failures.
- Autoscale fetch workers by queue lag.
- Autoscale parse workers by CPU and parse queue depth.
- Idempotent writes using URL/content hashes.

## Delivery Plan

### Phase 0: PoC Validation

Duration: 5 days.

Deliverables:

- 500-URL sample crawl.
- 100-URL labelled golden set.
- extraction and classification quality baseline.
- cost-per-page estimate.

### Phase 1: MVP Pipeline

Duration: weeks 2-4.

Deliverables:

- ingest, queue, fetch, parse, object storage, warehouse, serving index.
- basic dashboards.
- metadata API.

Success: process 1M URLs in 24 hours with no data loss.

### Phase 2: Scale-Out

Duration: weeks 5-8.

Deliverables:

- Bloom filter dedup.
- rate limits and circuit breakers.
- SimHash dedup.
- headless rendering tier.
- data quality gates.

Success: process 100M URLs in 17 hours, proving linear path to 1B in 7 days.

### Phase 3: Production Hardening

Duration: weeks 9-12.

Deliverables:

- full observability.
- runbooks.
- disaster recovery.
- cost optimization.
- regression suite.

## Blockers

Trivial:

- redirect chains
- parser edge cases
- encoding issues
- additive schema changes

Hard:

- anti-bot defenses
- legal and ToS boundaries
- JavaScript rendering cost
- per-domain politeness at scale
- classifier quality
- cost control at 1B URLs

Unknowns to resolve by PoC:

- page type distribution
- real domain politeness limits
- classification ground truth
- actual cost per page
- legal review by domain category

## Release Strategy

- Shadow mode on a 5% sample.
- Canary by domain bucket.
- Feature flags for rendering, classifiers, and schema changes.
- Rollback parser changes by reprocessing stored raw HTML.
- Rollback fetch workers by scaling down, fixing, and replaying queue messages.

## AI Usage Declaration

AI assistance was used for planning, architecture review, edge-case discovery, and code scaffolding. All outputs were reviewed and verified with local tests.
