from datetime import datetime, timezone

from crawler.fetcher import FetchResult
from crawler.service import build_crawl_record


def test_non_2xx_fetch_result_is_not_parsed():
    fetch = FetchResult(
        requested_url="https://example.com/private",
        final_url="https://example.com/private",
        status_code=403,
        html="<html><head><title>Access Denied</title></head><body><h1>Blocked</h1></body></html>",
        fetched_at=datetime.now(timezone.utc),
        duration_ms=10,
        errors=["http_status_403"],
        warnings=["blocked_by_anti_bot"],
    )

    record = build_crawl_record(fetch)

    assert record.http_status == 403
    assert record.title is None
    assert record.body_text is None
    assert record.word_count == 0
    assert record.errors == ["http_status_403"]
    assert "non_2xx_response_not_parsed" in record.warnings
