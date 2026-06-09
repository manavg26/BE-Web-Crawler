from __future__ import annotations

from crawler.classifier import classify_page_type, extract_topics
from crawler.fetcher import FetchResult, fetch_url
from crawler.parser import parse_html
from crawler.schema import CrawlRecord, Headings, StructuredData


async def crawl(url: str, respect_robots: bool = True) -> CrawlRecord:
    fetch = await fetch_url(url, respect_robots=respect_robots)
    return build_crawl_record(fetch)


def build_crawl_record(fetch: FetchResult) -> CrawlRecord:
    parsed = parse_html(fetch.html) if fetch.html else {}
    headings = parsed.get("headings") or Headings()
    structured_data = parsed.get("structured_data") or StructuredData()
    body_text = parsed.get("body_text")
    word_count = len(body_text.split()) if body_text else 0
    warnings = list(fetch.warnings)

    if fetch.html and word_count < 150:
        warnings.append("thin_content")
    if fetch.html and not structured_data.types:
        warnings.append("structured_data_missing")

    page_type = classify_page_type(
        fetch.final_url or url,
        structured_data,
        parsed.get("title"),
        headings.h1 + headings.h2,
    )

    topics = extract_topics([
        parsed.get("title"),
        parsed.get("meta_description"),
        body_text,
    ])

    return CrawlRecord(
        url=fetch.requested_url,
        final_url=fetch.final_url,
        http_status=fetch.status_code,
        fetched_at=fetch.fetched_at,
        fetch_duration_ms=fetch.duration_ms,
        page_type=page_type,
        language=parsed.get("language"),
        canonical=parsed.get("canonical"),
        title=parsed.get("title"),
        meta_description=parsed.get("meta_description"),
        meta_keywords=parsed.get("meta_keywords", []),
        og_title=parsed.get("og_title"),
        og_description=parsed.get("og_description"),
        og_image=parsed.get("og_image"),
        headings=headings,
        body_text=body_text,
        word_count=word_count,
        structured_data=structured_data,
        topics=topics,
        primary_category=topics[0].label if topics else None,
        topic_confidence=topics[0].score if topics else None,
        errors=fetch.errors,
        warnings=sorted(set(warnings)),
    )
