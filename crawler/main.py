from __future__ import annotations

from fastapi import FastAPI, Query

from crawler.schema import CrawlRecord, CrawlRequest
from crawler.service import crawl


app = FastAPI(
    title="BrightEdge Web Crawler",
    version="1.0.0",
    description="Proof-of-concept crawler for the BrightEdge scale home assignment.",
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl", response_model=CrawlRecord)
async def crawl_post(request: CrawlRequest) -> CrawlRecord:
    return await crawl(str(request.url))


@app.get("/crawl", response_model=CrawlRecord)
async def crawl_get(url: str = Query(..., min_length=1)) -> CrawlRecord:
    return await crawl(url)
