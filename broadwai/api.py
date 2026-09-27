import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from broadwai.collections import router as collections_router
from broadwai.config import Settings
from broadwai.image_review import ImageReviewer
from broadwai.images import ArticleImages
from broadwai.llm import ModelError, OpenAILanguageModel
from broadwai.models import Cover, CoverRequest, Feedback, IngestRequest
from broadwai.network import PublicFetcher
from broadwai.pipeline import CoverPipeline
from broadwai.reader_memory import ArticleLike
from broadwai.retrieval import Collector
from broadwai.sources import router as admin_router
from broadwai.store import Store
from broadwai.web_search import OpenAIWebSearch


def create_app(
    settings: Settings | None = None, *, store=None, model=None, collector=None, search=None
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        repository = store or Store(settings.database_url.get_secret_value())
        if store is None:
            await asyncio.to_thread(repository.open)
        llm = model
        if llm is None and settings.llm_ready:
            llm = OpenAILanguageModel(
                settings.openai_api_key.get_secret_value(),
                settings.summary_model,
                settings.editor_model,
                settings.max_article_chars,
            )
        app.state.store = repository
        app.state.model = llm
        app.state.collector = collector or Collector(
            repository,
            PublicFetcher(settings.request_timeout, settings.max_download_bytes),
        )
        app.state.search = search or OpenAIWebSearch(llm, settings.web_search_enabled)
        app.state.cover_lock = asyncio.Lock()
        app.state.source_lock = asyncio.Lock()
        app.state.images = ArticleImages(
            repository,
            PublicFetcher(settings.request_timeout, settings.max_download_bytes),
            ImageReviewer(
                repository, settings.openai_api_key.get_secret_value(), settings.image_review_model
            )
            if settings.image_review_enabled
            and settings.openai_api_key
            and settings.openai_api_key.get_secret_value()
            else None,
            require_review=settings.image_review_enabled,
        )
        try:
            yield
        finally:
            await app.state.images.close()
            if model is None and llm is not None:
                await llm.close()
            if store is None:
                repository.close()

    app = FastAPI(
        title="BroadwAI",
        version="0.1.0",
        lifespan=lifespan,
        description="Catalogue partagé et agent de création de couvertures.",
    )
    static = Path(__file__).with_name("static")
    app.mount("/admin/assets", StaticFiles(directory=static), name="admin-assets")
    app.include_router(admin_router)
    app.include_router(collections_router)

    # Optional production build. API/admin still work when the frontend is not built.
    reader_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (reader_dist / "index.html").is_file():
        app.mount("/reader", StaticFiles(directory=reader_dist, html=True), name="reader")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/admin")

    @app.get("/admin", include_in_schema=False)
    def admin():
        return FileResponse(static / "admin.html")

    @app.get("/admin/covers", include_in_schema=False)
    def cover_inspector():
        return FileResponse(static / "covers.html")

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "llm_configured": app.state.model is not None,
            "web_search_configured": app.state.search.enabled,
            "catalog": app.state.store.stats(),
        }

    @app.get("/v1/likes")
    def likes(user_id: str = Query(min_length=1, max_length=100)):
        return {"article_ids": app.state.store.liked_ids(user_id)}

    @app.put("/v1/likes")
    def set_like(event: ArticleLike):
        try:
            app.state.store.set_like(event)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"article_id": event.article_id, "liked": event.liked}

    @app.post("/v1/ingest")
    async def ingest(request: IngestRequest):
        if not request.feed_urls and not request.website_urls and not request.hacker_news:
            raise HTTPException(422, "Indiquer un flux, un site web ou activer Hacker News")
        return await app.state.collector.ingest(request)

    @app.get("/v1/articles")
    def articles(limit: int = Query(50, ge=1, le=200)):
        return [
            a.model_dump(exclude={"text", "excerpt", "transcript"})
            for a in app.state.store.articles(limit)
        ]

    @app.get("/v1/articles/{article_id}/image", include_in_schema=False)
    async def get_article_image(article_id: str):
        result = await app.state.images.get(article_id)
        if result is None:
            return Response(status_code=404, headers={"Cache-Control": "public, max-age=300"})
        body, media_type = result
        return Response(
            body,
            media_type=media_type,
            headers={
                "Cache-Control": "public, max-age=21600",
                "X-Content-Type-Options": "nosniff",
                "Cross-Origin-Resource-Policy": "same-origin",
            },
        )

    @app.post("/v1/covers", response_model=Cover)
    async def create_cover(request: CoverRequest):
        if app.state.model is None:
            raise HTTPException(503, "Configurer OPENAI_API_KEY, SUMMARY_MODEL et EDITOR_MODEL")
        if app.state.cover_lock.locked():
            raise HTTPException(429, "Une couverture est déjà en préparation ; réessayer ensuite")
        async with app.state.cover_lock:
            memory = await asyncio.to_thread(
                app.state.store.reading_memory, request.profile.user_id
            )
            request = request.model_copy(
                update={"profile": request.profile.model_copy(update={"reading_memory": memory})}
            )
            pipeline = CoverPipeline(
                app.state.store, app.state.collector, app.state.search, app.state.model, settings
            )
            try:
                async with asyncio.timeout(300):
                    return await pipeline.run(request)
            except TimeoutError as exc:
                raise HTTPException(
                    504, "Délai de génération dépassé ; fiches déjà créées conservées"
                ) from exc
            except ModelError as exc:
                raise HTTPException(
                    502, "Les appels aux modèles ont échoué ; aucune couverture enregistrée"
                ) from exc

    @app.get("/v1/covers")
    def list_covers(
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
        user_id: str | None = Query(None, min_length=1, max_length=100),
    ):
        if user_id is None:
            return app.state.store.list_covers(limit, offset)
        return app.state.store.list_covers(limit, offset, user_id=user_id)

    @app.get("/v1/library")
    def library(user_id: str = Query(min_length=1, max_length=100)):
        return app.state.store.library(user_id)

    @app.put("/v1/library/{cover_id}")
    def save_edition(cover_id: str, user_id: str = Query(min_length=1, max_length=100)):
        try:
            app.state.store.save_edition(user_id, cover_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"saved": True}

    @app.delete("/v1/library/{cover_id}")
    def remove_edition(cover_id: str, user_id: str = Query(min_length=1, max_length=100)):
        app.state.store.remove_edition(user_id, cover_id)
        return {"saved": False}

    @app.get("/v1/covers/{cover_id}", response_model=Cover)
    def get_cover(cover_id: str, user_id: str | None = Query(None, min_length=1, max_length=100)):
        cover = app.state.store.get_cover(cover_id)
        if cover is None or (user_id is not None and cover.user_id != user_id):
            raise HTTPException(404, "Couverture introuvable")
        # Older editions predate this metadata; enrich them from the local catalog.
        items = []
        for item in cover.items:
            article = app.state.store.get_article(item.article_id)
            if article is not None:
                item = item.model_copy(
                    update={
                        "reading_time_minutes": item.reading_time_minutes
                        or article.reading_time_minutes,
                        "image": article.image
                        if article.image_checked_at is not None
                        else article.image or item.image,
                        "image_checked": article.image_checked_at is not None or item.image_checked,
                    }
                )
            items.append(item)
        cover = cover.model_copy(update={"items": items})
        return cover

    @app.post("/v1/feedback", status_code=201)
    def feedback(event: Feedback):
        try:
            app.state.store.add_feedback(event)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"saved": True}

    return app


app = create_app()
