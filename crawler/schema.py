from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field


PageType = Literal["product", "article", "homepage", "category", "other"]
JobStatus = Literal["queued", "fetching", "fetched", "parsing", "completed", "failed"]


class Topic(BaseModel):
    label: str
    score: float = Field(ge=0.0, le=1.0)


class Headings(BaseModel):
    h1: list[str] = Field(default_factory=list)
    h2: list[str] = Field(default_factory=list)
    h3: list[str] = Field(default_factory=list)


class StructuredData(BaseModel):
    types: list[str] = Field(default_factory=list)
    json_ld: list[Any] = Field(default_factory=list)


class CrawlRequest(BaseModel):
    url: AnyHttpUrl


class CrawlJobAccepted(BaseModel):
    job_id: str
    status: JobStatus
    result_url: str


class CrawlJobResponse(BaseModel):
    job_id: str
    url: str
    status: JobStatus
    record: "CrawlRecord | None" = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class CrawlRecord(BaseModel):
    url: str
    final_url: str | None = None
    http_status: int | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    fetch_duration_ms: int | None = None
    page_type: PageType = "other"
    language: str | None = None
    canonical: str | None = None
    title: str | None = None
    meta_description: str | None = None
    meta_keywords: list[str] = Field(default_factory=list)
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    headings: Headings = Field(default_factory=Headings)
    body_text: str | None = None
    word_count: int = 0
    structured_data: StructuredData = Field(default_factory=StructuredData)
    topics: list[Topic] = Field(default_factory=list)
    primary_category: str | None = None
    topic_confidence: float | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
