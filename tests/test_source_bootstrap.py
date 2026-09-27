import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import psycopg
import pytest

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.daily_sources import DailySourceCollection, collection_slot, next_collection_at
from broadwai.models import utcnow
from broadwai.source_catalog import bundled_sources
from broadwai.sources import SourceInput
from scripts.validate_source_catalog import export_sources
from tests.admin_fakes import AdminCollector


def definitions(count=3):
    return [
        SourceInput(name=f"Source {i}", url=f"https://example.org/{i}/rss").model_dump()
        for i in range(count)
    ]


def report():
    return {"collected": 0, "article_ids": [], "errors": []}


def test_bundled_catalog_is_full_verified_export_and_independent_of_cwd(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    catalog = json.loads((root / "examples/source-catalog.json").read_text())
    monkeypatch.chdir(tmp_path)
    assert bundled_sources() == export_sources(catalog)
    assert Settings(_env_file=None).source_bootstrap_enabled


async def test_bootstrap_collects_immediately_once_preserving_existing_and_paused(
    pg_store, monkeypatch
):
    rows = definitions()
    monkeypatch.setattr("broadwai.daily_sources.bundled_sources", lambda: rows)
    paused = pg_store.save_source(
        {**rows[0], "name": "Mon nom", "enabled": False, "limit_per_source": 7}
    )
    existing = pg_store.save_source(rows[1])
    pg_store.record_collection(existing["id"], report())
    collector = AdminCollector(pg_store)
    now = utcnow()

    def service():
        return DailySourceCollection(
            pg_store,
            collector,
            asyncio.Lock(),
            enabled=False,
            bootstrap_enabled=True,
            clock=lambda: now,
        )

    daily = service()
    await daily.initialize()
    assert not collector.calls  # Registering the catalogue makes no network requests.
    assert len(pg_store.list_sources()) == 3
    assert (await daily.status())["bootstrap"]["pending"]
    await daily.run_due()
    assert len(collector.calls) == 1
    assert collector.calls[0].feed_urls == [rows[2]["url"]]
    assert pg_store.stats()["articles"] == 1
    state = await daily.status()
    assert state["bootstrap"]["completed_at"] == now
    assert state["next_run_at"] is None  # Bootstrap is independent of nightly scheduling.
    saved = next(row for row in pg_store.list_sources() if row["id"] == paused["id"])
    assert (saved["name"], saved["enabled"], saved["limit_per_source"]) == ("Mon nom", False, 7)

    deleted = next(row for row in pg_store.list_sources() if row["url"] == rows[2]["url"])
    pg_store.delete_source(deleted["id"])
    restarted = service()
    await restarted.initialize()
    await restarted.run_due()
    assert len(collector.calls) == 1
    assert len(pg_store.list_sources()) == 2  # A later restart must not undo admin deletion.
    now += timedelta(days=1)
    await restarted.run_due()
    assert len(collector.calls) == 1  # No nightly work when explicitly disabled.


async def test_bootstrap_continues_into_daily_collection_and_failed_feed_does_not_block(
    pg_store, monkeypatch
):
    monkeypatch.setattr("broadwai.daily_sources.bundled_sources", lambda: definitions(2))
    now = utcnow()
    collector = AsyncMock()
    collector.ingest.side_effect = [ValueError("Unavailable feed"), report()]
    daily = DailySourceCollection(
        pg_store, collector, asyncio.Lock(), bootstrap_enabled=True, clock=lambda: now
    )
    await daily.initialize()
    await daily.run_due()
    state = await daily.status()
    assert state["bootstrap"]["completed_at"]
    assert state["last_run"]["report"]["sources_with_errors"] == 1
    assert collector.ingest.await_count == 2
    await daily.run_due()
    assert collector.ingest.await_count == 2
    now = next_collection_at(now)
    collector.ingest.side_effect = None
    collector.ingest.return_value = report()
    await daily.run_due()
    assert collector.ingest.await_count == 4


async def test_interrupted_bootstrap_resumes_only_unfinished_sources(pg_store, monkeypatch):
    rows = definitions(8)
    monkeypatch.setattr("broadwai.daily_sources.bundled_sources", lambda: rows)
    hold = asyncio.Event()

    async def ingest(request):
        if request.feed_urls == [rows[0]["url"]]:
            return report()
        await hold.wait()
        return report()

    daily = DailySourceCollection(
        pg_store, AsyncMock(ingest=ingest), asyncio.Lock(), bootstrap_enabled=True
    )
    await daily.initialize()
    task = asyncio.create_task(daily.run_due())
    try:
        async with asyncio.timeout(3):
            while not any(s["last_collected_at"] for s in pg_store.list_sources()):
                await asyncio.sleep(0.01)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert (await daily.status())["last_run"]["status"] == "interrupted"
    assert (await daily.status())["bootstrap"]["pending"]
    collector = AsyncMock()
    collector.ingest.return_value = report()
    restarted = DailySourceCollection(pg_store, collector, asyncio.Lock(), bootstrap_enabled=True)
    await restarted.initialize()
    await restarted.run_due()
    assert collector.ingest.await_count == 7
    assert (await restarted.status())["bootstrap"]["completed_at"]


def test_concurrent_imports_and_daily_bootstrap_claims_are_exclusive(pg_store):
    now = utcnow()
    slot = collection_slot(now)
    with ThreadPoolExecutor(max_workers=2) as executor:
        imports = list(
            executor.map(
                lambda _: pg_store.initialize_source_catalog(definitions(), now, slot), range(2)
            )
        )
        claims = list(
            executor.map(
                lambda initial: pg_store.claim_source_collection(
                    slot, now, scheduled=not initial, bootstrap=initial
                ),
                [False, True],
            )
        )
    assert imports.count(3) == 1 and imports.count(None) == 1
    assert len(pg_store.list_sources()) == 3
    assert sum(token is not None for token in claims) == 1


def test_catalog_import_is_transactional(pg_store):
    rows = definitions()
    rows[-1]["name"] = None
    now = utcnow()
    with pytest.raises(psycopg.errors.NotNullViolation):
        pg_store.initialize_source_catalog(rows, now, next_collection_at(now))
    assert pg_store.list_sources() == []
    assert not pg_store.source_collection_status().get("catalog_imported_at")
    assert pg_store.initialize_source_catalog(definitions(), now, next_collection_at(now)) == 3


async def test_bootstrap_can_follow_already_completed_daily_slot(pg_store, monkeypatch):
    now = utcnow()
    slot = collection_slot(now)
    pg_store.initialize_source_collection(slot)
    token = pg_store.claim_source_collection(slot, now)
    pg_store.finish_source_collection(slot, token, now, {})
    monkeypatch.setattr("broadwai.daily_sources.bundled_sources", lambda: definitions(1))
    collector = AsyncMock()
    collector.ingest.return_value = report()
    daily = DailySourceCollection(pg_store, collector, asyncio.Lock(), bootstrap_enabled=True)
    await daily.initialize()
    await daily.run_due()
    collector.ingest.assert_awaited_once()
    assert (await daily.status())["bootstrap"]["completed_at"]


def test_old_worker_cannot_complete_bootstrap_before_imported_sources_are_collected(pg_store):
    now = utcnow()
    slot = collection_slot(now)
    pg_store.initialize_source_collection(slot)
    token = pg_store.claim_source_collection(slot, now)
    pg_store.initialize_source_catalog(definitions(1), now, next_collection_at(now))
    pg_store.finish_source_collection(slot, token, now, {})
    assert not pg_store.source_collection_status()["bootstrap_completed_at"]
    replacement = pg_store.claim_source_collection(slot, now, bootstrap=True)
    assert replacement
    pg_store.record_collection(pg_store.list_sources()[0]["id"], report())
    pg_store.finish_source_collection(slot, token, now, {})
    assert not pg_store.source_collection_status()["bootstrap_completed_at"]
    pg_store.finish_source_collection(slot, replacement, now, {})
    assert pg_store.source_collection_status()["bootstrap_completed_at"]


async def test_real_app_startup_imports_and_serves_http_while_collecting(pg_store, monkeypatch):
    monkeypatch.setattr("broadwai.api.Store", lambda _: pg_store)
    monkeypatch.setattr(pg_store, "close", lambda: None)
    monkeypatch.setattr("broadwai.daily_sources.bundled_sources", lambda: definitions(1))
    collecting = asyncio.Event()
    hold = asyncio.Event()

    async def ingest(request):
        collecting.set()
        await hold.wait()
        return report()

    settings = Settings(
        _env_file=None,
        openai_api_key=None,
        image_review_enabled=False,
        daily_editions_enabled=False,
        daily_source_collection_enabled=False,
    )
    app = create_app(settings, collector=AsyncMock(ingest=ingest))
    async with asyncio.timeout(5), app.router.lifespan_context(app):
        await collecting.wait()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["source_bootstrap_enabled"]
        assert len(pg_store.list_sources()) == 1
        assert (await app.state.daily_sources.status())["bootstrap"]["pending"]
    assert pg_store.source_collection_status()["last_run"]["status"] == "interrupted"
