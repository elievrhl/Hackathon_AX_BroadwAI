"""Daily editions run on the server, independently of browser sessions."""

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from broadwai.models import CoverRequest, utcnow

PARIS = ZoneInfo("Europe/Paris")
logger = logging.getLogger(__name__)


def edition_slot(now: datetime) -> datetime:
    local = now.astimezone(PARIS)
    day = local.date() - timedelta(days=local.hour < 4)
    return datetime.combine(day, time(4), PARIS).astimezone(UTC)


def next_edition_at(now: datetime) -> datetime:
    local = now.astimezone(PARIS)
    day = local.date() + timedelta(days=local.hour >= 4)
    return datetime.combine(day, time(4), PARIS).astimezone(UTC)


class DailyEditions:
    def __init__(self, store, generate, lock, *, enabled=True, clock=utcnow):
        self.store = store
        self.generate = generate
        self.lock = lock
        self.enabled = enabled
        self.clock = clock

    async def register(self, request: CoverRequest):
        now = self.clock()
        # Reading memory is refreshed from the database at generation time.
        request = request.model_copy(
            update={
                "profile": request.profile.model_copy(
                    update={
                        "reading_memory": {},
                        "edition_feedback": [],
                    }
                ),
            }
        )
        await asyncio.to_thread(self.store.save_daily_profile, request, next_edition_at(now), now)
        return await self.status(request.profile.user_id)

    async def status(self, user_id):
        now = self.clock()
        saved = await asyncio.to_thread(self.store.daily_edition_status, user_id)
        first_run = saved.get("first_run_at")
        run = saved.get("run")
        current = run if run and run["edition_date"] == edition_slot(now).date() else None
        state = "scheduled" if first_run else "unregistered"
        if current:
            state = {"completed": "ready"}.get(current["status"], current["status"])
            if state == "running" and current["started_at"] < now - timedelta(minutes=10):
                state = "failed"
        if not self.enabled:
            state = "disabled"
        return {
            "enabled": self.enabled,
            "registered": first_run is not None,
            "timezone": "Europe/Paris",
            "hour": 4,
            "next_run_at": max(first_run, next_edition_at(now)) if first_run else None,
            "status": state,
            "cover_id": current.get("cover_id") if current else None,
        }

    async def run_due(self):
        if not self.enabled:
            return
        while True:
            # An idle scheduler must not make manual API requests return 429.
            if not await asyncio.to_thread(
                self.store.has_due_daily_edition, edition_slot(self.clock())
            ):
                return
            # Claim after waiting for manual work: a queued job must not expire.
            async with self.lock:
                now = self.clock()
                job = await asyncio.to_thread(
                    self.store.claim_daily_edition, edition_slot(now), now
                )
                if job is None:
                    return
                user_id, day = job["user_id"], job["edition_date"]
                try:
                    async with asyncio.timeout(300):
                        cover = await self.generate(CoverRequest.model_validate(job["request"]))
                    await asyncio.to_thread(self.store.finish_daily_edition, user_id, day, cover.id)
                except asyncio.CancelledError:
                    await asyncio.to_thread(self.store.finish_daily_edition, user_id, day, None)
                    raise
                except Exception:
                    logger.exception("Daily edition failed")
                    await asyncio.to_thread(self.store.finish_daily_edition, user_id, day, None)

    async def serve(self):
        while True:
            try:
                await self.run_due()
            except Exception:
                logger.exception("Daily edition scheduler unavailable")
            await asyncio.sleep(30)
