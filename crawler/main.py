from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request

from crawler.database import CrawlJobStore
from crawler.logging_config import configure_logging, log_call
from crawler.pipeline import CrawlPipeline
from crawler.schema import CrawlJobAccepted, CrawlJobResponse, CrawlRecord, CrawlRequest
from crawler.service import crawl


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    store = CrawlJobStore()
    pipeline = CrawlPipeline(store)
    app.state.pipeline = pipeline
    await pipeline.start()
    try:
        yield
    finally:
        await pipeline.stop()


app = FastAPI(
    title="BrightEdge Web Crawler",
    version="1.0.0",
    description="Proof-of-concept crawler for the BrightEdge scale home assignment.",
    lifespan=lifespan,
)


@app.get("/health")
@log_call("health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl", response_model=CrawlJobAccepted, status_code=202)
@log_call("crawl_post")
async def crawl_post(request: Request, crawl_request: CrawlRequest) -> CrawlJobAccepted:
    return await request.app.state.pipeline.submit(str(crawl_request.url))


@app.get("/crawl/{job_id}", response_model=CrawlJobResponse)
@log_call("crawl_result")
async def crawl_result(request: Request, job_id: str) -> CrawlJobResponse:
    job = request.app.state.pipeline.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="crawl job not found")
    return job


@app.get("/crawl", response_model=CrawlRecord)
@log_call("crawl_get")
async def crawl_get(url: str = Query(..., min_length=1)) -> CrawlRecord:
    """Backward-compatible direct crawl endpoint for demos and smoke tests."""
    return await crawl(url)
