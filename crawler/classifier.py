from __future__ import annotations

import math
import re
from collections import Counter
from urllib.parse import urlparse

from crawler.schema import PageType, StructuredData, Topic


TOKEN_RE = re.compile(r"[a-z][a-z0-9-]{2,}", re.IGNORECASE)
STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "article",
    "from",
    "have",
    "into",
    "more",
    "page",
    "that",
    "the",
    "this",
    "with",
    "your",
}


def classify_page_type(url: str, structured_data: StructuredData, title: str | None, headings: list[str]) -> PageType:
    schema_types = {item.lower() for item in structured_data.types}
    path = urlparse(url).path.lower()
    title_text = (title or "").lower()
    heading_text = " ".join(headings).lower()

    if {"product", "offer", "review"} & schema_types or any(part in path for part in ("/dp/", "/product/", "/p/")):
        return "product"
    if {"article", "newsarticle", "blogposting"} & schema_types or any(part in path for part in ("/blog/", "/news/", "/article/")):
        return "article"
    if path in {"", "/"}:
        return "homepage"
    if any(part in path for part in ("/category/", "/collections/", "/c/")) or "category" in title_text + heading_text:
        return "category"
    return "other"


def extract_topics(text_parts: list[str | None], limit: int = 5) -> list[Topic]:
    text = " ".join(part for part in text_parts if part)
    tokens = [token.lower().strip("-") for token in TOKEN_RE.findall(text)]
    tokens = [token for token in tokens if token not in STOPWORDS and not token.isdigit()]
    if not tokens:
        return []

    counts = Counter(tokens)
    max_count = max(counts.values())
    topics: list[Topic] = []
    for token, count in counts.most_common(limit):
        score = min(1.0, round(0.35 + 0.65 * math.log1p(count) / math.log1p(max_count), 3))
        topics.append(Topic(label=token, score=score))
    return topics
