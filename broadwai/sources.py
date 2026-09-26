import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, model_validator

from broadwai.models import IngestRequest, Model
from broadwai.network import RetrievalError, validate_destination


class SourceInput(Model):
    name: str = Field(min_length=1, max_length=150)
    kind: Literal["rss", "hacker_news", "website"] = "rss"
    url: str = Field("", max_length=2000)
    enabled: bool = True
    limit_per_source: int = Field(20, ge=1, le=50)

    @model_validator(mode="after")
    def validate_source(self):
        if self.kind == "hacker_news":
            self.url = "https://hacker-news.firebaseio.com/v0/topstories.json"
        else:
            try:
                self.url = validate_destination(self.url)
            except RetrievalError as exc:
                raise ValueError(str(exc)) from exc
        return self


router = APIRouter(prefix="/v1", tags=["Administration"])


class ProposalReview(Model):
    approve: bool


@router.get("/source-proposals")
def list_proposals(request: Request):
    return request.app.state.store.list_proposals()


@router.post("/source-proposals/{proposal_id}/review")
async def review_proposal(proposal_id: str, body: ProposalReview, request: Request):
    require_idle(request)
    result = request.app.state.store.review_proposal(proposal_id, body.approve)
    if result is None:
        raise HTTPException(404, "Proposition introuvable")
    return result


def require_idle(request: Request):
    if request.app.state.source_lock.locked():
        raise HTTPException(409, "Collecte en cours ; réessayer une fois terminée")


@router.get("/sources")
def list_sources(request: Request):
    return request.app.state.store.list_sources()


@router.post("/sources", status_code=201)
async def create_source(body: SourceInput, request: Request):
    require_idle(request)
    try:
        return request.app.state.store.save_source(body.model_dump())
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.put("/sources/{source_id}")
async def update_source(source_id: str, body: SourceInput, request: Request):
    require_idle(request)
    try:
        result = request.app.state.store.save_source(body.model_dump(), source_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    if result is None:
        raise HTTPException(404, "Source introuvable")
    return result


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str, request: Request):
    require_idle(request)
    if not request.app.state.store.delete_source(source_id):
        raise HTTPException(404, "Source introuvable")


async def collect_sources(request: Request, source_id: str | None = None):
    require_idle(request)
    async with request.app.state.source_lock:
        store = request.app.state.store
        sources = store.list_sources()
        if source_id:
            sources = [s for s in sources if s["id"] == source_id]
            if not sources:
                raise HTTPException(404, "Source introuvable")
        else:
            sources = [s for s in sources if s["enabled"]]
        results = []
        for source in sources:
            body = IngestRequest(
                feed_urls=[source["url"]] if source["kind"] == "rss" else [],
                website_urls=[source["url"]] if source["kind"] == "website" else [],
                hacker_news=source["kind"] == "hacker_news",
                limit_per_source=source["limit_per_source"],
            )
            try:
                async with asyncio.timeout(120):
                    report = await request.app.state.collector.ingest(body)
            except (TimeoutError, RetrievalError) as exc:
                report = {
                    "article_ids": [],
                    "collected": 0,
                    "errors": [{"error": f"Collecte interrompue : {type(exc).__name__}"}],
                }
            store.record_collection(source["id"], report)
            results.append({"source_id": source["id"], "name": source["name"], **report})
        return {"results": results}


@router.post("/sources/collect")
async def collect_all(request: Request):
    return await collect_sources(request)


@router.post("/sources/{source_id}/collect")
async def collect_one(source_id: str, request: Request):
    return await collect_sources(request, source_id)


@router.get("/admin/articles")
def browse_articles(
    request: Request,
    q: str = Query("", max_length=200),
    source_id: str | None = None,
    status: Literal["excerpt", "extracted"] | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    return request.app.state.store.browse_articles(q, source_id, status, offset, limit)


@router.get("/admin/articles/{article_id}")
def article_detail(article_id: str, request: Request):
    result = request.app.state.store.article_detail(article_id)
    if result is None:
        raise HTTPException(404, "Article introuvable")
    return result
