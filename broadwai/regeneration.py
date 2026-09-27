"""One reader-requested regeneration per Paris calendar day, with durable feedback."""

import asyncio
from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException
from pydantic import Field, field_validator

from broadwai.daily_editions import PARIS
from broadwai.models import CoverRequest, Model, utcnow


class RegenerationRequest(Model):
    cover_id: str = Field(min_length=1, max_length=100)
    reason: str = Field("", max_length=1000)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value):
        value = value.strip()
        if value and (len(value) < 2 or not any(c.isalnum() for c in value)):
            raise ValueError("Expliquez pourquoi vous souhaitez une nouvelle une")
        return value


class Regenerations:
    def __init__(self, store, generate, lock, *, enabled=True, clock=utcnow):
        self.store = store
        self.generate = generate
        self.lock = lock
        self.enabled = enabled
        self.clock = clock

    async def status(self, user_id):
        now = self.clock()
        day = now.astimezone(PARIS).date()
        run = await asyncio.to_thread(self.store.get_regeneration, user_id, day)
        state = run["status"] if run else "available"
        if run and state == "running" and run["started_at"] < now - timedelta(minutes=10):
            state = "failed"
        estimate = run["estimated_seconds"] if run else 120
        elapsed = (
            max(0, ((run.get("finished_at") or now) - run["started_at"]).total_seconds())
            if run
            else 0
        )
        return {
            "available": self.enabled and run is None,
            "status": state if self.enabled or run else "unavailable",
            "timezone": "Europe/Paris",
            "next_available_at": datetime.combine(
                day + timedelta(days=1), time(), PARIS
            ).astimezone(UTC)
            if run
            else None,
            "cover_id": run["cover_id"] if run else None,
            "can_reset": run is not None and state != "running",
            "started_at": run["started_at"] if run else None,
            "server_time": now,
            "elapsed_seconds": round(elapsed),
            "estimated_seconds": estimate,
        }

    async def reset(self, user_id):
        if await asyncio.to_thread(self.store.get_daily_profile, user_id) is None:
            raise HTTPException(404, "Profil lecteur introuvable.")
        now = self.clock()
        try:
            reset = await asyncio.to_thread(
                self.store.reset_regeneration, user_id, now.astimezone(PARIS).date(), now
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"reset": reset, "regeneration": await self.status(user_id)}

    async def regenerate(self, user_id, request: RegenerationRequest):
        if not self.enabled:
            raise HTTPException(503, "La régénération est momentanément indisponible.")
        if self.lock.locked():
            raise HTTPException(429, "Une une est déjà en préparation. Réessayez dans un instant.")
        async with self.lock:
            previous = await asyncio.to_thread(self.store.get_cover, request.cover_id)
            if previous is None or previous.user_id != user_id:
                raise HTTPException(404, "Cette édition est introuvable.")
            saved = await asyncio.to_thread(self.store.get_daily_profile, user_id)
            if saved is None:
                raise HTTPException(409, "Enregistrez vos préférences avant de refaire votre une.")
            now = self.clock()
            day = now.astimezone(PARIS).date()
            if await asyncio.to_thread(self.store.get_regeneration, user_id, day):
                raise HTTPException(
                    409,
                    "Votre régénération du jour est déjà utilisée. "
                    "Vous pourrez réessayer demain, à partir de minuit (Paris).",
                )
            latest = await asyncio.to_thread(self.store.list_covers, 1, 0, user_id=user_id)
            if not latest or latest[0]["id"] != previous.id:
                raise HTTPException(
                    409,
                    "Une édition plus récente est disponible. "
                    "Revenez à votre une actuelle pour la régénérer.",
                )
            generation = CoverRequest.model_validate(saved)
            # Only this replacement excludes the rejected edition's articles. The reason,
            # reloaded by prepare_cover, continues to guide subsequent daily editions.
            generation.profile.seen_article_ids = list(
                dict.fromkeys(
                    [
                        *[item.article_id for item in previous.items],
                        *generation.profile.seen_article_ids,
                    ]
                )
            )[:2000]
            estimate = await asyncio.to_thread(self.store.estimate_regeneration_seconds, user_id)
            claimed = await asyncio.to_thread(
                self.store.claim_regeneration, user_id, day, request, now, estimate
            )
            if not claimed:
                raise HTTPException(
                    409,
                    "Votre régénération du jour est déjà utilisée. "
                    "Vous pourrez réessayer demain, à partir de minuit (Paris).",
                )
            # Keep the reservation on failure or cancellation: ambiguous paid calls
            # must never be replayed by refreshing or by another worker.
            try:
                async with asyncio.timeout(300):
                    cover = await self.generate(generation)
                await asyncio.to_thread(
                    self.store.finish_regeneration, claimed, cover.id, self.clock()
                )
                return cover
            except (Exception, asyncio.CancelledError) as exc:
                await asyncio.to_thread(self.store.finish_regeneration, claimed, None, self.clock())
                if isinstance(exc, TimeoutError):
                    raise HTTPException(
                        504, "La préparation de votre nouvelle une a expiré."
                    ) from exc
                raise
