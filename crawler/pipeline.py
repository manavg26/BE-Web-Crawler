from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import uuid4

from crawler.database import CrawlJobStore
from crawler.fetcher import FetchResult, fetch_url
from crawler.schema import CrawlJobAccepted, CrawlJobResponse
from crawler.service import build_crawl_record


FETCH_TOPIC = "crawl.fetch"
PARSE_TOPIC = "crawl.parse"
POLL_INTERVAL_SECONDS = 0.1


class CrawlPipeline:
    """PoC pipeline with Kafka-like topics and separate fetch/parse workers."""

    def __init__(self, store: CrawlJobStore) -> None:
        self.store = store
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._tasks:
            return
        self._tasks.append(asyncio.create_task(self._fetch_worker(), name="fetch-worker"))
        self._tasks.append(asyncio.create_task(self._parse_worker(), name="parse-worker"))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def submit(self, url: str) -> CrawlJobAccepted:
        job_id = uuid4().hex
        self.store.create_job(job_id, url)
        self.store.publish(FETCH_TOPIC, job_id, {"job_id": job_id, "url": url})
        return CrawlJobAccepted(job_id=job_id, status="queued", result_url=f"/crawl/{job_id}")

    def get(self, job_id: str) -> CrawlJobResponse | None:
        return self.store.get_job(job_id)

    async def _fetch_worker(self) -> None:
        while True:
            message = self.store.poll(FETCH_TOPIC)
            if message is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            job_id = message.payload["job_id"]
            url = message.payload["url"]
            try:
                self.store.update_status(job_id, "fetching")
                fetch_result = await fetch_url(url)
                self.store.update_status(job_id, "fetched")
                self.store.publish(PARSE_TOPIC, job_id, {"job_id": job_id, "fetch_result": _fetch_to_payload(fetch_result)})
                self.store.ack(message.message_id)
            except Exception as exc:  # pragma: no cover - defensive worker guard
                self.store.update_status(job_id, "failed", f"fetch_worker_error:{exc.__class__.__name__}")
                self.store.ack(message.message_id)

    async def _parse_worker(self) -> None:
        while True:
            message = self.store.poll(PARSE_TOPIC)
            if message is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
                continue

            job_id = message.payload["job_id"]
            try:
                self.store.update_status(job_id, "parsing")
                record = build_crawl_record(_fetch_from_payload(message.payload["fetch_result"]))
                self.store.save_record(job_id, record)
                self.store.ack(message.message_id)
            except Exception as exc:  # pragma: no cover - defensive worker guard
                self.store.update_status(job_id, "failed", f"parse_worker_error:{exc.__class__.__name__}")
                self.store.ack(message.message_id)


def _fetch_to_payload(fetch_result: FetchResult) -> dict:
    return {
        "requested_url": fetch_result.requested_url,
        "final_url": fetch_result.final_url,
        "status_code": fetch_result.status_code,
        "html": fetch_result.html,
        "fetched_at": fetch_result.fetched_at.isoformat(),
        "duration_ms": fetch_result.duration_ms,
        "errors": fetch_result.errors,
        "warnings": fetch_result.warnings,
    }


def _fetch_from_payload(payload: dict) -> FetchResult:
    return FetchResult(
        requested_url=payload["requested_url"],
        final_url=payload["final_url"],
        status_code=payload["status_code"],
        html=payload["html"],
        fetched_at=datetime.fromisoformat(payload["fetched_at"]),
        duration_ms=payload["duration_ms"],
        errors=payload.get("errors", []),
        warnings=payload.get("warnings", []),
    )
