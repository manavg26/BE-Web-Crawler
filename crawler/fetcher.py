from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


USER_AGENT = "BrightEdgeCrawlerDemo/1.0 (+https://brightedge.com/crawler-assignment)"
DEFAULT_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3


@dataclass
class FetchResult:
    requested_url: str
    final_url: str | None
    status_code: int | None
    html: str
    fetched_at: datetime
    duration_ms: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RobotsCache:
    def __init__(self) -> None:
        self._cache: dict[str, RobotFileParser] = {}

    async def can_fetch(self, client: httpx.AsyncClient, url: str, user_agent: str) -> tuple[bool, str | None]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False, "invalid_url"

        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = f"{origin}/robots.txt"
        if origin not in self._cache:
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                response = await client.get(robots_url, timeout=5)
                if response.status_code < 400:
                    parser.parse(response.text.splitlines())
                else:
                    parser.parse([])
            except httpx.HTTPError:
                parser.parse([])
            self._cache[origin] = parser

        allowed = self._cache[origin].can_fetch(user_agent, url)
        return allowed, None if allowed else "blocked_by_robots_txt"


robots_cache = RobotsCache()


async def fetch_url(url: str, respect_robots: bool = True) -> FetchResult:
    started = time.perf_counter()
    fetched_at = datetime.now(timezone.utc)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    errors: list[str] = []
    warnings: list[str] = []

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=DEFAULT_TIMEOUT_SECONDS) as client:
        if respect_robots:
            can_fetch, reason = await robots_cache.can_fetch(client, url, USER_AGENT)
            if not can_fetch:
                duration_ms = int((time.perf_counter() - started) * 1000)
                return FetchResult(url, url, None, "", fetched_at, duration_ms, warnings=[reason or "robots_disallowed"])

        response: httpx.Response | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.get(url)
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
                warnings.append(f"retryable_status_{response.status_code}")
            except httpx.HTTPError as exc:
                errors.append(f"fetch_error:{exc.__class__.__name__}")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(0.25 * (2**attempt))

    duration_ms = int((time.perf_counter() - started) * 1000)
    if response is None:
        return FetchResult(url, url, None, "", fetched_at, duration_ms, errors=errors, warnings=warnings)

    html = response.text or ""
    if response.status_code in {403, 429, 503}:
        warnings.append("blocked_by_anti_bot")
    if response.status_code >= 400:
        errors.append(f"http_status_{response.status_code}")

    return FetchResult(
        requested_url=url,
        final_url=str(response.url),
        status_code=response.status_code,
        html=html,
        fetched_at=fetched_at,
        duration_ms=duration_ms,
        errors=errors,
        warnings=warnings,
    )
