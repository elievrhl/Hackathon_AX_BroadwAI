import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from broadwai.daily_sources import DailySourceCollection, collection_slot, next_collection_at
from broadwai.sources import SourceInput, collect_source_batch
from tests.admin_fakes import AdminStore


def at(value):
    return datetime.fromisoformat(value)


@pytest.mark.parametrize(
    ("now", "slot", "next_run"),
    [
        ("2026-09-27T00:59:59+00:00", "2026-09-26T01:00:00+00:00", "2026-09-27T01:00:00+00:00"),
        ("2026-09-27T01:00:00+00:00", "2026-09-27T01:00:00+00:00", "2026-09-28T01:00:00+00:00"),
        ("2026-03-28T02:00:00+00:00", "2026-03-28T02:00:00+00:00", "2026-03-29T01:00:00+00:00"),
        ("2026-10-24T01:00:00+00:00", "2026-10-24T01:00:00+00:00", "2026-10-25T02:00:00+00:00"),
        ("2026-10-25T01:30:00+00:00", "2026-10-24T01:00:00+00:00", "2026-10-25T02:00:00+00:00"),
    ],
)
def test_collection_at_three_in_paris_including_dst(now, slot, next_run):
    assert collection_slot(at(now)) == at(slot)
    assert next_collection_at(at(now)) == at(next_run)


def source(store, index=0, **changes):
    return store.save_source(
        SourceInput(
            name=f"Source {index}", url=f"https://example.org/{index}/rss", **changes
        ).model_dump()
    )


def report(*, errors=None):
    return {"collected": 0, "article_ids": [], "errors": errors or []}


async def test_batch_bounds_concurrency_and_persists_failures_without_aborting_other_sources():
    store = AdminStore()
    sources = [source(store, index) for index in range(12)]
    running = peak = 0

    async def ingest(request):
        nonlocal running, peak
        assert request.limit_per_source == 50
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if request.feed_urls == [sources[0]["url"]]:
            raise ValueError("Broken source")
        return report()

    results = await collect_source_batch(store, AsyncMock(ingest=ingest), sources)
    assert peak == 5
    assert len(results) == 12
    assert sum(bool(row["errors"]) for row in results) == 1
    assert all(row["last_collected_at"] for row in store.list_sources())


async def test_disabled_schedule_does_not_touch_store_or_collector():
    store, collector = AsyncMock(), AsyncMock()
    daily = DailySourceCollection(store, collector, asyncio.Lock(), enabled=False)
    await daily.initialize()
    await daily.run_due()
    assert not (await daily.status())["enabled"]
    assert not store.mock_calls and not collector.mock_calls


async def test_schedule_waits_until_three_and_restart_does_not_repeat_completed_day(pg_store):
    now = at("2026-09-26T12:00:00+00:00")
    collector = AsyncMock()
    collector.ingest.return_value = report()
    source(pg_store)
    source(pg_store, 1, enabled=False)
    daily = DailySourceCollection(pg_store, collector, asyncio.Lock(), clock=lambda: now)
    await daily.initialize()
    await daily.run_due()
    collector.ingest.assert_not_awaited()
    assert (await daily.status())["next_run_at"] == at("2026-09-27T01:00:00+00:00")
    now = at("2026-09-27T01:00:00+00:00")
    await daily.run_due()
    collector.ingest.assert_awaited_once()
    assert (await daily.status())["last_run"]["status"] == "completed"
    restarted = DailySourceCollection(pg_store, collector, asyncio.Lock(), clock=lambda: now)
    await restarted.initialize()
    await restarted.run_due()
    collector.ingest.assert_awaited_once()
    now = at("2026-10-02T08:00:00+00:00")
    await restarted.run_due()
    assert collector.ingest.await_count == 2  # Only the latest missed day.


async def test_interruption_resumes_remaining_sources_and_respects_manual_lock(pg_store):
    now = at("2026-09-26T12:00:00+00:00")
    first = source(pg_store)
    source(pg_store, 1)
    collector = AsyncMock()
    collector.ingest.side_effect = asyncio.CancelledError
    lock = asyncio.Lock()
    daily = DailySourceCollection(pg_store, collector, lock, clock=lambda: now)
    await daily.initialize()
    now = at("2026-09-27T01:00:00+00:00")
    pg_store.record_collection(first["id"], report())
    async with lock:
        await daily.run_due()
    collector.ingest.assert_not_awaited()
    with pytest.raises(asyncio.CancelledError):
        await daily.run_due()
    assert (await daily.status())["last_run"]["status"] == "interrupted"
    collector.ingest.side_effect = None
    collector.ingest.return_value = report()
    await daily.run_due()
    assert collector.ingest.await_count == 2
    saved = (await daily.status())["last_run"]
    assert saved["status"] == "completed"
    assert saved["report"]["already_collected"] == 1
    assert saved["report"]["processed"] == 1


def test_postgres_claims_exclusive_and_stale_owner_cannot_finish_new_run(pg_store):
    now = at("2026-09-27T01:00:00+00:00")
    slot = collection_slot(now)
    pg_store.initialize_source_collection(slot)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: pg_store.claim_source_collection(slot, now), range(2)))
    token = next(value for value in claims if value)
    assert sum(value is not None for value in claims) == 1
    later = now + timedelta(minutes=6)
    replacement = pg_store.claim_source_collection(slot, later)
    assert replacement and replacement != token
    assert not pg_store.touch_source_collection(slot, token, later)
    pg_store.finish_source_collection(slot, token, later, {})
    assert pg_store.source_collection_status()["last_run"]["status"] == "running"
    pg_store.finish_source_collection(slot, replacement, later, {})
    assert pg_store.claim_source_collection(slot, later) is None
