import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.daily_editions import DailyEditions, edition_slot, next_edition_at
from broadwai.models import CoverRequest
from tests.fakes import FakeCollector, FakeSearch, MemoryStore, ScriptedModel


def at(value):
    return datetime.fromisoformat(value)


def request(user="alice", notes=""):
    return CoverRequest(
        profile={
            "user_id": user,
            "interests": [{"topic": "Science"}],
            "notes": notes,
        },
        discover_videos=True,
        discover_podcasts=True,
    )


@pytest.mark.parametrize(
    ("now", "slot", "next_run"),
    [
        ("2026-09-27T01:59:59+00:00", "2026-09-26T02:00:00+00:00", "2026-09-27T02:00:00+00:00"),
        ("2026-09-27T02:00:00+00:00", "2026-09-27T02:00:00+00:00", "2026-09-28T02:00:00+00:00"),
        ("2026-03-28T03:00:00+00:00", "2026-03-28T03:00:00+00:00", "2026-03-29T02:00:00+00:00"),
        ("2026-10-24T02:00:00+00:00", "2026-10-24T02:00:00+00:00", "2026-10-25T03:00:00+00:00"),
    ],
)
def test_paris_schedule_including_daylight_saving(now, slot, next_run):
    assert edition_slot(at(now)) == at(slot)
    assert next_edition_at(at(now)) == at(next_run)


async def test_registration_waits_until_four_then_runs_once_with_latest_profile():
    store = MemoryStore()
    now = at("2026-09-26T12:00:00+00:00")
    generate = AsyncMock(return_value=SimpleNamespace(id="cover"))
    daily = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    await daily.register(request())
    await daily.run_due()
    generate.assert_not_awaited()
    now = at("2026-09-27T01:59:59+00:00")
    await daily.register(request(notes="Astronomie"))
    await daily.run_due()
    generate.assert_not_awaited()
    now += timedelta(seconds=1)
    await daily.run_due()
    generate.assert_awaited_once()
    assert generate.call_args.args[0].profile.notes == "Astronomie"
    assert generate.call_args.args[0].discover_podcasts
    assert generate.call_args.args[0].discover_videos
    assert (await daily.status("alice"))["status"] == "ready"
    await daily.register(request(notes="Biologie"))
    await daily.run_due()
    generate.assert_awaited_once()
    now += timedelta(days=1)
    await daily.run_due()
    assert generate.await_count == 2
    assert generate.call_args.args[0].profile.notes == "Biologie"


async def test_restart_catches_up_only_latest_day_and_does_not_repeat_paid_failures():
    store = MemoryStore()
    now = at("2026-09-20T12:00:00+00:00")
    generate = AsyncMock(
        side_effect=[RuntimeError("Provider failure"), SimpleNamespace(id="cover")]
    )
    daily = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    await daily.register(request())
    await daily.register(request("bob"))
    now = at("2026-09-27T14:00:00+00:00")
    await daily.run_due()
    assert generate.await_count == 2
    assert len(store.daily_runs) == 2  # No seven-day backlog.
    assert (await daily.status("alice"))["status"] == "failed"
    assert (await daily.status("bob"))["status"] == "ready"
    restarted = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    await restarted.run_due()
    assert generate.await_count == 2


async def test_interrupted_run_is_not_replayed_and_waits_for_manual_lock():
    store = MemoryStore()
    now = at("2026-09-26T12:00:00+00:00")
    generate = AsyncMock(return_value=SimpleNamespace(id="cover"))
    lock = asyncio.Lock()
    daily = DailyEditions(store, generate, lock, clock=lambda: now)
    await daily.register(request())
    now = at("2026-09-27T02:00:00+00:00")
    await lock.acquire()
    task = asyncio.create_task(daily.run_due())
    await asyncio.sleep(0)
    assert store.daily_runs == {}
    # Simulate another worker claiming the date, then crashing.
    store.claim_daily_edition(edition_slot(now), now)
    now += timedelta(minutes=11)
    lock.release()
    await task
    generate.assert_not_awaited()
    assert (await daily.status("alice"))["status"] == "failed"


def test_daily_api_registers_profiles_without_generating_and_isolates_status():
    store = MemoryStore()
    model = ScriptedModel()
    with TestClient(
        create_app(
            Settings(_env_file=None),
            store=store,
            model=model,
            collector=FakeCollector(store),
            search=FakeSearch(),
        )
    ) as client:
        path = "/v1/readers/alice/daily-edition"
        assert client.get(path).json()["status"] == "unregistered"
        response = client.put(path, json=request().model_dump(mode="json"))
        assert response.status_code == 200
        result = response.json()
        assert result["registered"] and result["enabled"]
        assert result["hour"] == 4 and result["timezone"] == "Europe/Paris"
        assert result["next_run_at"]
        assert store.covers == {} and store.daily_runs == {}
        assert not client.get("/v1/readers/bob/daily-edition").json()["registered"]
        assert client.put(path, json=request("bob").model_dump(mode="json")).status_code == 422


def test_disabled_scheduler_still_preserves_profile_and_reports_unavailability():
    store = MemoryStore()
    with TestClient(
        create_app(
            Settings(_env_file=None, openai_api_key=None, summary_model="", editor_model=""),
            store=store,
        )
    ) as client:
        result = client.put("/v1/readers/alice/daily-edition", json=request().model_dump()).json()
        assert result["registered"] and not result["enabled"]
        assert result["status"] == "disabled"
        assert not store.daily_runs


def test_postgres_claim_is_unique_across_workers_and_registration_is_durable(pg_store):
    now = at("2026-09-26T12:00:00+00:00")
    pg_store.save_daily_profile(request(), next_edition_at(now), now)
    pg_store.save_daily_profile(request(notes="Latest preferences"), next_edition_at(now), now)
    assert pg_store.claim_daily_edition(edition_slot(now), now) is None
    now = at("2026-09-27T02:00:00+00:00")
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda _: pg_store.claim_daily_edition(edition_slot(now), now),
                range(2),
            )
        )
    assert sum(value is not None for value in claims) == 1
    job = next(value for value in claims if value)
    assert job["request"]["profile"]["notes"] == "Latest preferences"
    pg_store.finish_daily_edition("alice", job["edition_date"], None)
    assert pg_store.claim_daily_edition(edition_slot(now), now) is None
    assert pg_store.daily_edition_status("alice")["run"]["status"] == "failed"
    assert pg_store.daily_edition_status("bob")["first_run_at"] is None
    # Re-registering on another day preserves eligibility and does not postpone it.
    now += timedelta(days=1)
    pg_store.save_daily_profile(request(notes="Updated"), next_edition_at(now), now)
    assert (
        pg_store.claim_daily_edition(edition_slot(now), now)["request"]["profile"]["notes"]
        == "Updated"
    )
