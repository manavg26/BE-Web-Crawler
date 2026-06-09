from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any

try:
    from selectolax.parser import HTMLParser as SelectolaxParser
except ImportError:  # pragma: no cover - exercised only without optional dependency
    SelectolaxParser = None

try:
    import trafilatura
except ImportError:  # pragma: no cover - exercised only without optional dependency
    trafilatura = None

from crawler.schema import Headings, StructuredData


SPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")


def clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = SPACE_RE.sub(" ", unescape(value)).strip()
    return cleaned or None


class FallbackHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title: str | None = None
        self.meta: dict[str, str] = {}
        self.links: dict[str, str] = {}
        self.headings = Headings()
        self.json_ld_raw: list[str] = []
        self._current: str | None = None
        self._buffer: list[str] = []
        self._script_type: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag in {"title", "h1", "h2", "h3"}:
            self._current = tag
            self._buffer = []
        elif tag == "meta":
            key = (attr.get("name") or attr.get("property") or "").lower()
            if key and "content" in attr:
                self.meta[key] = attr["content"]
        elif tag == "link" and attr.get("rel", "").lower() == "canonical":
            self.links["canonical"] = attr.get("href", "")
        elif tag == "script":
            self._script_type = attr.get("type", "").lower()
            self._current = "script"
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._current:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag != self._current:
            return
        text = clean_text(" ".join(self._buffer))
        if text:
            if tag == "title":
                self.title = text
            elif tag in {"h1", "h2", "h3"}:
                getattr(self.headings, tag).append(text)
            elif tag == "script" and self._script_type == "application/ld+json":
                self.json_ld_raw.append(" ".join(self._buffer))
        self._current = None
        self._buffer = []
        self._script_type = None


def parse_html(html: str) -> dict[str, Any]:
    if SelectolaxParser is not None:
        return _parse_with_selectolax(html)
    return _parse_with_fallback(html)


def _parse_with_selectolax(html: str) -> dict[str, Any]:
    tree = SelectolaxParser(html)

    def text(selector: str) -> str | None:
        node = tree.css_first(selector)
        return clean_text(node.text()) if node else None

    def attr(selector: str, name: str) -> str | None:
        node = tree.css_first(selector)
        return clean_text(node.attributes.get(name)) if node else None

    headings = Headings(
        h1=[value for node in tree.css("h1") if (value := clean_text(node.text()))],
        h2=[value for node in tree.css("h2") if (value := clean_text(node.text()))],
        h3=[value for node in tree.css("h3") if (value := clean_text(node.text()))],
    )

    json_ld_raw = [
        node.text()
        for node in tree.css('script[type="application/ld+json"]')
        if clean_text(node.text())
    ]

    body_text = extract_body_text(html)
    return {
        "title": text("title"),
        "language": attr("html", "lang"),
        "canonical": attr('link[rel="canonical"]', "href"),
        "meta_description": attr('meta[name="description"]', "content"),
        "meta_keywords": split_keywords(attr('meta[name="keywords"]', "content")),
        "og_title": attr('meta[property="og:title"]', "content"),
        "og_description": attr('meta[property="og:description"]', "content"),
        "og_image": attr('meta[property="og:image"]', "content"),
        "headings": headings,
        "body_text": body_text,
        "structured_data": parse_json_ld(json_ld_raw),
    }


def _parse_with_fallback(html: str) -> dict[str, Any]:
    parser = FallbackHTMLParser()
    parser.feed(html)
    return {
        "title": parser.title,
        "language": None,
        "canonical": clean_text(parser.links.get("canonical")),
        "meta_description": clean_text(parser.meta.get("description")),
        "meta_keywords": split_keywords(parser.meta.get("keywords")),
        "og_title": clean_text(parser.meta.get("og:title")),
        "og_description": clean_text(parser.meta.get("og:description")),
        "og_image": clean_text(parser.meta.get("og:image")),
        "headings": parser.headings,
        "body_text": extract_body_text(html),
        "structured_data": parse_json_ld(parser.json_ld_raw),
    }


def split_keywords(value: str | None) -> list[str]:
    if not value:
        return []
    return [part for item in value.split(",") if (part := clean_text(item))]


def extract_body_text(html: str) -> str | None:
    if trafilatura is not None:
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if cleaned := clean_text(extracted):
            return cleaned

    text = TAG_RE.sub(" ", html)
    return clean_text(text)


def parse_json_ld(raw_blocks: list[str]) -> StructuredData:
    values: list[Any] = []
    types: set[str] = set()
    for raw in raw_blocks:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        values.append(parsed)
        collect_schema_types(parsed, types)
    return StructuredData(types=sorted(types), json_ld=values)


def collect_schema_types(value: Any, types: set[str]) -> None:
    if isinstance(value, dict):
        schema_type = value.get("@type")
        if isinstance(schema_type, str):
            types.add(schema_type)
        elif isinstance(schema_type, list):
            types.update(item for item in schema_type if isinstance(item, str))
        for nested in value.values():
            collect_schema_types(nested, types)
    elif isinstance(value, list):
        for item in value:
            collect_schema_types(item, types)
