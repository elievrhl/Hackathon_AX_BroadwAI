"""Collect active sources at 03:00 Europe/Paris, with durable restart recovery."""

import asyncio
import logging
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from broadwai.models import utcnow
from broadwai.source_catalog import bundled_sources
from broadwai.sources import collect_source_batch

PARIS = ZoneInfo("Europe/Paris")
logger = logging.getLogger(__name__)


def collection_slot(now):
    local = now.astimezone(PARIS)
    day = local.date() - timedelta(days=local.hour < 3)
    return datetime.combine(day, time(3), PARIS).astimezone(UTC)


def next_collection_at(now):
    local = now.astimezone(PARIS)
    day = local.date() + timedelta(days=local.hour >= 3)
    return datetime.combine(day, time(3), PARIS).astimezone(UTC)


class DailySourceCollection:
    def __init__(
        self, store, collector, lock, *, enabled=True, bootstrap_enabled=False, clock=utcnow
    ):
        self.store = store
        self.collector = collector
        self.lock = lock
        self.enabled = enabled
        self.bootstrap_enabled = bootstrap_enabled
        self.clock = clock

    async def initialize(self):
        if self.bootstrap_enabled:
            now = self.clock()
            definitions = await asyncio.to_thread(bundled_sources)
            added = await asyncio.to_thread(
                self.store.initialize_source_catalog, definitions, now, next_collection_at(now)
            )
            if added is not None:
                logger.info("Initial source catalogue imported: %s new sources", added)
        if self.enabled:
            await asyncio.to_thread(
                self.store.initialize_source_collection, next_collection_at(self.clock())
            )

    async def status(self):
        saved = (
            await asyncio.to_thread(self.store.source_collection_status)
            if self.enabled or self.bootstrap_enabled
            else {}
        )
        first = saved.get("first_run_at")
        return {
            "enabled": self.enabled,
            "timezone": "Europe/Paris",
            "hour": 3,
            "next_run_at": (
                max(first, next_collection_at(self.clock())) if self.enabled and first else None
            ),
            "last_run": saved.get("last_run"),
            "bootstrap": {
                "enabled": self.bootstrap_enabled,
                "imported_at": saved.get("catalog_imported_at"),
                "completed_at": saved.get("bootstrap_completed_at"),
                "pending": bool(saved.get("catalog_imported_at"))
                and not saved.get("bootstrap_completed_at"),
            },
        }

    async def run_due(self):
        if not (self.enabled or self.bootstrap_enabled) or self.lock.locked():
            return
        # One lock for manual and scheduled collections in this process; the DB
        # claim prevents a second scheduler from starting the same night's work.
        async with self.lock:
            now = self.clock()
            slot = collection_slot(now)
            token = await asyncio.to_thread(
                self.store.claim_source_collection,
                slot,
                now,
                scheduled=self.enabled,
                bootstrap=self.bootstrap_enabled,
            )
            if token is None:
                return
            try:
                sources = await asyncio.to_thread(self.store.list_sources)
                active = [source for source in sources if source["enabled"]]
                pending = [
                    source
                    for source in active
                    if not source.get("last_collected_at") or source["last_collected_at"] < slot
                ]

                async def heartbeat():
                    owned = await asyncio.to_thread(
                        self.store.touch_source_collection, slot, token, self.clock()
                    )
                    if not owned:
                        raise RuntimeError("Source collection lease lost")

                results = await collect_source_batch(
                    self.store, self.collector, pending, heartbeat=heartbeat
                )
                report = {
                    "sources": len(active),
                    "processed": len(results),
                    "already_collected": len(active) - len(pending),
                    "collected": sum(row["collected"] for row in results),
                    "sources_with_errors": sum(bool(row["errors"]) for row in results),
                }
                await asyncio.to_thread(
                    self.store.finish_source_collection, slot, token, self.clock(), report
                )
                logger.info("Daily source collection complete: %s", report)
            except (Exception, asyncio.CancelledError):
                await asyncio.to_thread(
                    self.store.finish_source_collection,
                    slot,
                    token,
                    self.clock(),
                    {"error": "Collecte interrompue ; reprise des sources restantes."},
                    interrupted=True,
                )
                raise

    async def serve(self):
        while True:
            try:
                await self.run_due()
            except Exception:
                logger.exception("Daily source collection unavailable")
            await asyncio.sleep(30)
