import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient as AuthenticatedClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.daily_editions import DailyEditions, edition_slot, next_edition_at
from broadwai.models import Cover, CoverRequest
from tests.auth_fakes import AuthMemoryStore
from tests.client import TestClient
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)


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
    store.list_covers = Mock(return_value=[{"id": "existing-edition"}])
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


@pytest.mark.parametrize("store_fixture", [None, "pg_store"])
async def test_first_edition_is_due_now_once_even_for_previously_registered_readers(
    request, store_fixture
):
    store = request.getfixturevalue(store_fixture) if store_fixture else MemoryStore()
    now = at("2026-09-27T01:59:00+00:00")  # Still before 4 a.m. in Paris.
    payload = CoverRequest(profile={"user_id": "alice", "interests": [{"topic": "Science"}]})
    store.put_cover(Cover(
        id="other-reader-cover", user_id="bob", title="Bob", status="partial",
        items=[], trace=[], warnings=[], usage={},
    ))
    # A profile saved by the previous version used to wait until tomorrow.
    store.save_daily_profile(payload, next_edition_at(now), now)
    async def prepare(_):
        cover = Cover(
            id="first-cover", user_id="alice", title="Alice", status="partial",
            items=[], trace=[], warnings=[], usage={},
        )
        store.put_cover(cover)
        return cover

    generate = AsyncMock(side_effect=prepare)
    daily = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    assert (await daily.register(payload))["status"] == "queued"
    await daily.run_due()
    assert (await daily.status("alice"))["cover_id"] == "first-cover"
    # Refreshing, signing in again, and another worker cannot repeat the attempt.
    restarted = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    await asyncio.gather(daily.register(payload), restarted.register(payload))
    await asyncio.gather(daily.run_due(), restarted.run_due())
    generate.assert_awaited_once()


async def test_registration_wakes_idle_scheduler_and_failed_first_edition_is_not_retried():
    store = MemoryStore()
    now = at("2026-09-27T12:00:00+00:00")
    generate = AsyncMock(side_effect=RuntimeError("Provider unavailable"))
    daily = DailyEditions(store, generate, asyncio.Lock(), clock=lambda: now)
    idle = asyncio.Event()
    original_has_due = store.has_due_daily_edition

    loop = asyncio.get_running_loop()

    def has_due(slot):
        result = original_has_due(slot)
        if not result:
            loop.call_soon_threadsafe(idle.set)
        return result

    store.has_due_daily_edition = has_due
    task = asyncio.create_task(daily.serve())
    try:
        await asyncio.wait_for(idle.wait(), timeout=2)
        await daily.register(request())
        async with asyncio.timeout(2):
            while (await daily.status("alice"))["status"] != "failed":
                await asyncio.sleep(0.01)
        await daily.register(request())
        await daily.run_due()
        generate.assert_awaited_once()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


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
    # Existing readers only synchronize their next scheduled edition.
    store.list_covers = Mock(return_value=[{"id": "existing-edition"}])
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


def test_authenticated_first_visit_prepares_an_edition_and_login_reuses_it():
    store = AuthMemoryStore()
    store.put_article(article())
    app = create_app(
        Settings(_env_file=None, openai_api_key=None), store=store,
        model=ScriptedModel([finalize_first]), collector=FakeCollector(store), search=FakeSearch(),
    )
    with AuthenticatedClient(app, headers={
        "Origin": "http://127.0.0.1:5173", "X-Kiosque-Request": "1",
    }) as client:
        credentials = {"email": "reader@example.com", "password": "test-reader-long-password"}
        response = client.post("/v1/auth/register", json={**credentials, "name": "Camille"})
        assert response.status_code == 201
        session = response.json()
        client.headers["X-Kiosque-CSRF"] = session["csrf_token"]
        user = session["account"]["id"]
        payload = CoverRequest(profile={"user_id": user, "interests": [{"topic": "Python"}]})
        path = f"/v1/readers/{user}/daily-edition"
        assert client.get("/v1/covers", params={"user_id": user}).json() == []
        assert client.put(path, json=payload.model_dump(mode="json")).status_code == 200

        async def wait_for_edition():
            async with asyncio.timeout(3):
                while (await app.state.daily_editions.status(user))["status"] != "ready":
                    await asyncio.sleep(0.01)

        client.portal.call(wait_for_edition)
        rows = client.get("/v1/covers", params={"user_id": user}).json()
        assert len(rows) == 1 and rows[0]["item_count"] > 0
        assert client.post("/v1/auth/logout").status_code == 204
        logged_in = client.post("/v1/auth/login", json=credentials)
        assert logged_in.status_code == 200
        client.headers["X-Kiosque-CSRF"] = logged_in.json()["csrf_token"]
        assert client.put(path, json=payload.model_dump(mode="json")).status_code == 200
        client.portal.call(app.state.daily_editions.run_due)
        assert client.get("/v1/covers", params={"user_id": user}).json() == rows
        assert len(store.daily_runs) == 1


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
