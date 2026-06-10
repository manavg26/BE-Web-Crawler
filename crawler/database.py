from __future__ import annotations

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from crawler.schema import CrawlJobResponse, CrawlRecord, JobStatus


DEFAULT_DB_PATH = "crawl_results.db"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrokerMessage:
    message_id: int
    topic: str
    key: str
    payload: dict


class CrawlJobStore:
    """Small SQLite-backed store used as a local stand-in for PostgreSQL."""

    def __init__(self, path: str | None = None) -> None:
        self.path = path or os.getenv("CRAWLER_DB_PATH", DEFAULT_DB_PATH)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self.init()

    def init(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_jobs (
                job_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                record_json TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_crawl_jobs_url ON crawl_jobs(url)")
        self._connection.execute("CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status)")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS broker_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic TEXT NOT NULL,
                message_key TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                claimed_at TEXT,
                acked_at TEXT
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_broker_messages_topic_status
            ON broker_messages(topic, status, message_id)
            """
        )
        self._connection.commit()

    def create_job(self, job_id: str, url: str) -> None:
        logger.info("job_created", extra={"job_id": job_id, "url": url})
        now = _now()
        self._connection.execute(
            """
            INSERT INTO crawl_jobs (job_id, url, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (job_id, url, "queued", now, now),
        )
        self._connection.commit()

    def update_status(self, job_id: str, status: JobStatus, error: str | None = None) -> None:
        logger.info("job_status_updated", extra={"job_id": job_id, "status": status, "error": error})
        self._connection.execute(
            """
            UPDATE crawl_jobs
            SET status = ?, error = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, error, _now(), job_id),
        )
        self._connection.commit()

    def save_record(self, job_id: str, record: CrawlRecord) -> None:
        logger.info(
            "job_record_saved",
            extra={"job_id": job_id, "status": "completed", "http_status": record.http_status},
        )
        self._connection.execute(
            """
            UPDATE crawl_jobs
            SET status = ?, record_json = ?, error = NULL, updated_at = ?
            WHERE job_id = ?
            """,
            ("completed", record.model_dump_json(), _now(), job_id),
        )
        self._connection.commit()

    def get_job(self, job_id: str) -> CrawlJobResponse | None:
        row = self._connection.execute(
            """
            SELECT job_id, url, status, record_json, error, created_at, updated_at
            FROM crawl_jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        record = CrawlRecord.model_validate(json.loads(row["record_json"])) if row["record_json"] else None
        return CrawlJobResponse(
            job_id=row["job_id"],
            url=row["url"],
            status=row["status"],
            record=record,
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def publish(self, topic: str, key: str, payload: dict) -> int:
        cursor = self._connection.execute(
            """
            INSERT INTO broker_messages (topic, message_key, payload_json, status, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (topic, key, json.dumps(payload), "pending", _now()),
        )
        self._connection.commit()
        logger.info("broker_message_published", extra={"topic": topic, "key": key, "message_id": cursor.lastrowid})
        return int(cursor.lastrowid)

    def poll(self, topic: str) -> BrokerMessage | None:
        row = self._connection.execute(
            """
            SELECT message_id, topic, message_key, payload_json
            FROM broker_messages
            WHERE topic = ? AND status = ?
            ORDER BY message_id
            LIMIT 1
            """,
            (topic, "pending"),
        ).fetchone()
        if row is None:
            return None

        self._connection.execute(
            """
            UPDATE broker_messages
            SET status = ?, claimed_at = ?
            WHERE message_id = ?
            """,
            ("in_progress", _now(), row["message_id"]),
        )
        self._connection.commit()
        logger.info(
            "broker_message_claimed",
            extra={"topic": row["topic"], "key": row["message_key"], "message_id": row["message_id"]},
        )
        return BrokerMessage(
            message_id=row["message_id"],
            topic=row["topic"],
            key=row["message_key"],
            payload=json.loads(row["payload_json"]),
        )

    def ack(self, message_id: int) -> None:
        self._connection.execute(
            """
            UPDATE broker_messages
            SET status = ?, acked_at = ?
            WHERE message_id = ?
            """,
            ("acked", _now(), message_id),
        )
        self._connection.commit()
        logger.info("broker_message_acked", extra={"message_id": message_id})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
