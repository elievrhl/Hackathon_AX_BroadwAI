import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from broadwai.auth import authorize_request
from broadwai.auth import router as auth_router
from broadwai.collections import router as collections_router
from broadwai.config import Settings
from broadwai.daily_editions import DailyEditions
from broadwai.dictation import GradiumDictation
from broadwai.dictation import router as dictation_router
from broadwai.image_review import ImageReviewer
from broadwai.images import ArticleImages
from broadwai.llm import BudgetExceeded, ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import (
    Cover,
    CoverRequest,
    EditionFeedback,
    Feedback,
    IngestRequest,
    PreferenceCreate,
    PreferenceUpdate,
)
from broadwai.network import PublicFetcher
from broadwai.pipeline import CoverPipeline
from broadwai.preferences import PreferenceConflict
from broadwai.reader_chat import ReaderMessage, check_replay, preference_snapshot
from broadwai.reader_memory import ArticleLike
from broadwai.regeneration import RegenerationRequest, Regenerations
from broadwai.retrieval import Collector, refresh_media_sources
from broadwai.saved_articles import router as saved_articles_router
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
        app.state.settings = settings
        app.state.model = llm
        app.state.collector = collector or Collector(
            repository,
            PublicFetcher(settings.request_timeout, settings.max_download_bytes),
        )
        app.state.search = search or OpenAIWebSearch(llm, settings.web_search_enabled)
        app.state.cover_lock = asyncio.Lock()
        app.state.source_lock = asyncio.Lock()
        app.state.reader_chat_lock = asyncio.Lock()
        app.state.dictation = GradiumDictation(
            settings.gradium_api_key.get_secret_value() if settings.gradium_api_key else None
        )
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
        app.state.daily_editions = DailyEditions(
            repository,
            prepare_cover,
            app.state.cover_lock,
            enabled=settings.daily_editions_enabled and llm is not None,
        )
        app.state.regenerations = Regenerations(
            repository,
            prepare_cover,
            app.state.cover_lock,
            enabled=llm is not None,
        )
        daily_task = asyncio.create_task(app.state.daily_editions.serve())
        try:
            yield
        finally:
            daily_task.cancel()
            with suppress(asyncio.CancelledError):
                await daily_task
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
        dependencies=[Depends(authorize_request)],
    )
    static = Path(__file__).with_name("static")
    app.mount("/admin/assets", StaticFiles(directory=static), name="admin-assets")
    app.include_router(admin_router)
    app.include_router(collections_router)
    app.include_router(saved_articles_router)
    app.include_router(auth_router)
    app.include_router(dictation_router)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/v1/") and not request.url.path.endswith("/image"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    # Optional production build. API/admin still work when the frontend is not built.
    reader_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if (reader_dist / "index.html").is_file():
        app.mount("/reader", StaticFiles(directory=reader_dist, html=True), name="reader")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/reader/" if (reader_dist / "index.html").is_file() else "/admin")

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
            "daily_editions_enabled": app.state.daily_editions.enabled,
        }

    @app.get("/v1/likes")
    def likes(user_id: str = Query(min_length=1, max_length=100)):
        return {"article_ids": app.state.store.liked_ids(user_id)}

    @app.get("/v1/source-directory")
    def source_directory():
        return [
            {key: row.get(key) for key in ("name", "url", "kind", "enabled", "article_count")}
            for row in app.state.store.list_sources()
        ]

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
            return await prepare_cover(request)

    async def prepare_cover(request: CoverRequest):
        memory = await asyncio.to_thread(app.state.store.reading_memory, request.profile.user_id)
        feedback = await asyncio.to_thread(
            app.state.store.recent_edition_feedback,
            request.profile.user_id,
            app.state.regenerations.clock(),
        )
        request = request.model_copy(
            update={
                "profile": request.profile.model_copy(
                    update={
                        "reading_memory": memory,
                        "edition_feedback": [
                            EditionFeedback.model_validate(row) for row in feedback
                        ],
                    }
                )
            }
        )
        pipeline = CoverPipeline(
            app.state.store, app.state.collector, app.state.search, app.state.model, settings
        )
        try:
            async with asyncio.timeout(300):
                if (request.discover_videos and request.max_videos) or (
                    request.discover_podcasts and request.max_podcasts
                ):
                    if not app.state.source_lock.locked():
                        async with app.state.source_lock:
                            reports = await refresh_media_sources(
                                app.state.store,
                                app.state.collector,
                                videos=bool(request.discover_videos and request.max_videos),
                                podcasts=bool(request.discover_podcasts and request.max_podcasts),
                            )
                        pipeline.log("media_refreshed", sources=reports)
                        if any(report["errors"] for report in reports):
                            pipeline.warnings.append(
                                "Certains flux vidéo ou podcast sont indisponibles ; "
                                "la sélection utilise le catalogue disponible."
                            )
                return await pipeline.run(request)
        except TimeoutError as exc:
            raise HTTPException(
                504, "Délai de génération dépassé ; fiches déjà créées conservées"
            ) from exc
        except ModelError as exc:
            raise HTTPException(
                502, "Les appels aux modèles ont échoué ; aucune couverture enregistrée"
            ) from exc

    @app.put("/v1/readers/{user_id}/daily-edition")
    async def register_daily_edition(user_id: str, request: CoverRequest):
        if user_id != request.profile.user_id:
            raise HTTPException(422, "Le profil doit correspondre au compte")
        return await app.state.daily_editions.register(request)

    @app.get("/v1/readers/{user_id}/daily-edition")
    async def daily_edition_status(user_id: str):
        return await app.state.daily_editions.status(user_id)

    @app.get("/v1/readers/{user_id}/regeneration")
    async def regeneration_status(user_id: str):
        return await app.state.regenerations.status(user_id)

    @app.post("/v1/readers/{user_id}/regeneration", response_model=Cover)
    async def regenerate_edition(user_id: str, request: RegenerationRequest):
        return await app.state.regenerations.regenerate(user_id, request)

    @app.get("/v1/admin/editions")
    async def admin_editions(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0)):
        rows = await asyncio.to_thread(app.state.store.list_daily_profiles, limit, offset)
        for row in rows:
            row["schedule"] = await app.state.daily_editions.status(row["user_id"])
            row["regeneration"] = await app.state.regenerations.status(row["user_id"])
        return {
            "profiles": rows,
            "llm_configured": app.state.model is not None,
            "daily_editions_enabled": app.state.daily_editions.enabled,
            "preparing": app.state.cover_lock.locked(),
        }

    @app.post("/v1/admin/readers/{user_id}/regeneration/reset")
    async def admin_reset_regeneration(user_id: str):
        return await app.state.regenerations.reset(user_id)

    @app.post("/v1/admin/readers/{user_id}/covers", response_model=Cover)
    async def admin_generate_cover(user_id: str):
        saved = await asyncio.to_thread(app.state.store.get_daily_profile, user_id)
        if saved is None:
            raise HTTPException(404, "Profil absent : ouvrir le lecteur et choisir ses sujets")
        return await create_cover(CoverRequest.model_validate(saved))

    @app.get("/v1/covers")
    def list_covers(
        request: Request,
        limit: int = Query(30, ge=1, le=100),
        offset: int = Query(0, ge=0),
        user_id: str | None = Query(None, min_length=1, max_length=100),
    ):
        if not request.state.account["is_admin"]:
            user_id = request.state.account["id"]
        if user_id is None:
            return app.state.store.list_covers(limit, offset)
        return app.state.store.list_covers(limit, offset, user_id=user_id)

    @app.get("/v1/archives")
    def archives(user_id: str = Query(min_length=1, max_length=100)):
        return app.state.store.archives(user_id)

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
    def get_cover(
        cover_id: str,
        request: Request,
        user_id: str | None = Query(None, min_length=1, max_length=100),
    ):
        if not request.state.account["is_admin"]:
            user_id = request.state.account["id"]
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
                        "format": article.format,
                        "media": article.media,
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
            preference = app.state.store.add_feedback(event)
        except PreferenceConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"saved": True, "preference": preference}

    @app.get("/v1/readers/{user_id}/feedback/{cover_id}")
    def reader_feedback(user_id: str, cover_id: str):
        try:
            return app.state.store.feedback_for_cover(user_id, cover_id)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/v1/readers/{user_id}/preferences")
    def reader_preferences(user_id: str):
        return app.state.store.list_preferences(user_id)

    @app.get("/v1/readers/{user_id}/messages")
    def reader_messages(user_id: str):
        return app.state.store.list_reader_messages(user_id)

    @app.post("/v1/readers/{user_id}/messages", status_code=201)
    async def reader_message(user_id: str, request: ReaderMessage):
        if request.profile.user_id != user_id:
            raise HTTPException(422, "Le message et la fiche doivent concerner le même lecteur")
        if app.state.reader_chat_lock.locked():
            raise HTTPException(429, "Kiosque lit déjà un message. Réessayez dans un instant.")
        async with app.state.reader_chat_lock:
            repository = app.state.store
            try:
                previous = await asyncio.to_thread(
                    repository.get_reader_message, user_id, request.id
                )
                if previous:
                    return check_replay(previous, request)
                if app.state.model is None:
                    raise HTTPException(
                        503, "Kiosque ne peut pas lire vos messages pour le moment."
                    )
                rows = await asyncio.to_thread(
                    repository.list_preferences, user_id, active_only=True
                )
                history = await asyncio.to_thread(repository.list_reader_messages, user_id)
                state = {
                    "profile": request.profile.model_dump(mode="json"),
                    "preferences": [p.model_dump(mode="json") for p in rows],
                    "conversation": [
                        {"message": t["message"], "reply": t["reply"]} for t in history[-6:]
                    ],
                    "message": request.message,
                }
                budget = RunBudget(limits={"reader_chat": 1}, max_tokens=40000)
                async with asyncio.timeout(55):
                    reply = await app.state.model.reader_message(state, budget)
                return await asyncio.to_thread(
                    repository.save_reader_message,
                    user_id,
                    request,
                    reply,
                    preference_snapshot(rows),
                    budget.report(),
                )
            except PreferenceConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except TimeoutError as exc:
                raise HTTPException(
                    504, "Kiosque n’a pas répondu à temps. Votre fiche est inchangée."
                ) from exc
            except (ModelError, BudgetExceeded, ValueError) as exc:
                raise HTTPException(
                    502,
                    "Kiosque n’a pas pu mettre à jour votre fiche. "
                    "Réessayez ou précisez votre message.",
                ) from exc

    @app.post("/v1/readers/{user_id}/preferences", status_code=201)
    def create_preference(user_id: str, value: PreferenceCreate):
        if not 1 <= len(user_id) <= 100:
            raise HTTPException(422, "Identifiant lecteur invalide")
        try:
            return app.state.store.create_preference(user_id, value)
        except PreferenceConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.put("/v1/readers/{user_id}/preferences/{preference_id}")
    def update_preference(user_id: str, preference_id: str, value: PreferenceUpdate):
        try:
            return app.state.store.update_preference(user_id, preference_id, value)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PreferenceConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.delete("/v1/readers/{user_id}/preferences/{preference_id}")
    def delete_preference(user_id: str, preference_id: str, revision: int = Query(ge=1)):
        try:
            return app.state.store.update_preference(user_id, preference_id, revision=revision)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PreferenceConflict as exc:
            raise HTTPException(409, str(exc)) from exc

    return app


app = create_app()
