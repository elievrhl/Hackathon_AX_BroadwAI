import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.daily_editions import PARIS, next_edition_at
from broadwai.models import Cover, EditorialIntent
from broadwai.regeneration import RegenerationRequest, Regenerations
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)
from tests.test_pipeline import pipeline, request


def at(value):
    return datetime.fromisoformat(value)


def seed(store, user="alice", now=None):
    now = now or at("2026-09-27T12:00:00+00:00")
    cover = Cover(
        user_id=user,
        title="Votre une",
        created_at=now,
        status="partial",
        items=[],
        trace=[],
        warnings=[],
        usage={},
    )
    store.put_cover(cover)
    profile = request().model_copy(deep=True)
    profile.profile.user_id = user
    store.save_daily_profile(profile, next_edition_at(now), now)
    return cover


def regeneration(cover):
    return RegenerationRequest(
        cover_id=cover.id, reason="Davantage de sciences, moins de politique"
    )


@pytest.mark.parametrize(
    ("start", "reset"),
    [
        ("2026-09-27T21:59:59+00:00", "2026-09-27T22:00:00+00:00"),
        ("2026-10-25T00:30:00+00:00", "2026-10-25T23:00:00+00:00"),
        ("2026-03-29T00:30:00+00:00", "2026-03-29T22:00:00+00:00"),
    ],
)
async def test_allowance_is_per_paris_day_and_reader_and_survives_restart(start, reset):
    store = MemoryStore()
    now = at(start)
    cover = seed(store)
    generate = AsyncMock(return_value=cover)
    service = Regenerations(store, generate, asyncio.Lock(), clock=lambda: now)
    assert (await service.status("alice"))["available"]
    await service.regenerate("alice", regeneration(cover))
    state = await service.status("alice")
    assert state["status"] == "completed" and not state["available"]
    assert state["next_available_at"] == at(reset)
    assert (await service.status("bob"))["available"]
    restarted = Regenerations(store, generate, asyncio.Lock(), clock=lambda: now)
    with pytest.raises(HTTPException) as exc:
        await restarted.regenerate("alice", regeneration(cover))
    assert exc.value.status_code == 409
    generate.assert_awaited_once()
    now = at(reset)
    assert (await restarted.status("alice"))["available"]
    await restarted.regenerate("alice", regeneration(cover))
    assert generate.await_count == 2


async def test_simultaneous_workers_only_generate_once():
    store = MemoryStore()
    cover = seed(store)
    generate = AsyncMock(return_value=cover)
    now = at("2026-09-27T12:00:00+00:00")
    services = [Regenerations(store, generate, asyncio.Lock(), clock=lambda: now) for _ in range(2)]
    results = await asyncio.gather(
        *(s.regenerate("alice", regeneration(cover)) for s in services),
        return_exceptions=True,
    )
    generate.assert_awaited_once()
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1


@pytest.mark.parametrize("failure", [RuntimeError("Provider failure"), asyncio.CancelledError()])
async def test_failed_or_cancelled_attempt_keeps_feedback_and_daily_allowance(failure):
    store = MemoryStore()
    now = at("2026-09-27T12:00:00+00:00")
    cover = seed(store)
    generate = AsyncMock(side_effect=failure)
    service = Regenerations(store, generate, asyncio.Lock(), clock=lambda: now)
    with pytest.raises(type(failure)):
        await service.regenerate("alice", regeneration(cover))
    assert (await service.status("alice"))["status"] == "failed"
    assert not (await service.status("alice"))["available"]
    assert store.get_cover(cover.id) == cover
    assert store.recent_edition_feedback("alice", now)[0]["reason"] == regeneration(cover).reason


async def test_busy_disabled_and_invalid_requests_do_not_spend_allowance():
    store = MemoryStore()
    cover = seed(store)
    generate = AsyncMock(return_value=cover)
    lock = asyncio.Lock()
    service = Regenerations(store, generate, lock)
    await lock.acquire()
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("alice", regeneration(cover))
    assert exc.value.status_code == 429
    lock.release()
    service.enabled = False
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("alice", regeneration(cover))
    assert exc.value.status_code == 503
    service.enabled = True
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("bob", regeneration(cover))
    assert exc.value.status_code == 404
    newer = seed(store, now=cover.created_at + timedelta(hours=1))
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("alice", regeneration(cover))
    assert exc.value.status_code == 409
    del store.daily_profiles["alice"]
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("alice", regeneration(newer))
    assert exc.value.status_code == 409
    assert not store.regenerations
    generate.assert_not_awaited()


async def test_generation_timeout_reports_failure_and_retains_allowance():
    store = MemoryStore()
    cover = seed(store)
    service = Regenerations(store, AsyncMock(side_effect=TimeoutError), asyncio.Lock())
    with pytest.raises(HTTPException) as exc:
        await service.regenerate("alice", regeneration(cover))
    assert exc.value.status_code == 504
    assert (await service.status("alice"))["status"] == "failed"
    assert not (await service.status("alice"))["available"]


@pytest.mark.parametrize("comment", [{}, {"reason": ""}, {"reason": " "}, {"reason": "   "}])
def test_api_regenerates_without_comment_and_still_enforces_daily_limit(comment):
    store = MemoryStore([article()])
    original = seed(store)
    app = create_app(
        Settings(_env_file=None),
        store=store,
        model=ScriptedModel([finalize_first]),
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    with TestClient(app) as client:
        path = "/v1/readers/alice/regeneration"
        payload = {"cover_id": original.id, **comment}
        response = client.post(path, json=payload)
        assert response.status_code == 200, response.text
        assert response.json()["items"]
        assert client.post(path, json=payload).status_code == 409
        assert not client.get(path).json()["available"]
        assert not store.recent_edition_feedback("alice", app.state.regenerations.clock())


def test_api_replaces_articles_and_reloads_feedback_for_future_editions():
    store = MemoryStore([article(1), article(2)])
    model = ScriptedModel([finalize_first, finalize_first])
    model.interpret = AsyncMock(wraps=model.interpret)
    app = create_app(
        Settings(_env_file=None),
        store=store,
        model=model,
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    with TestClient(app) as client:
        now = app.state.regenerations.clock()
        app.state.regenerations.clock = lambda: now
        original = client.post("/v1/covers", json=request().model_dump(mode="json")).json()
        payload = {"cover_id": original["id"], "reason": "  Davantage de sciences  "}
        path = "/v1/readers/alice/regeneration"
        client.put("/v1/readers/alice/daily-edition", json=request().model_dump(mode="json"))
        for reason in ["!!", "a", "x" * 1001]:
            assert client.post(path, json={**payload, "reason": reason}).status_code == 422
        assert client.post("/v1/readers/bob/regeneration", json=payload).status_code == 404
        assert client.get(path).json()["available"]
        response = client.post(path, json=payload)
        assert response.status_code == 200, response.text
        replacement = response.json()
        assert replacement["items"]
        assert replacement["id"] != original["id"]
        assert {i["article_id"] for i in original["items"]}.isdisjoint(
            i["article_id"] for i in replacement["items"]
        )
        feedback = model.interpret.call_args.args[0]["profile"]["edition_feedback"]
        assert feedback[0]["reason"] == "Davantage de sciences"
        assert feedback[0]["previous_titles"] == [original["items"][0]["title"]]
        assert client.get(path).json()["cover_id"] == replacement["id"]
        assert client.post(path, json=payload).status_code == 409
        assert len(store.covers) == 2
        # Re-saving the browser profile cannot erase feedback or forge more feedback.
        forged = request().model_dump(mode="json")
        forged["profile"]["edition_feedback"] = [
            {
                "reason": "forged",
                "created_at": now.isoformat(),
                "previous_titles": [],
            }
        ]
        client.put("/v1/readers/alice/daily-edition", json=forged)
        assert store.get_daily_profile("alice")["profile"]["edition_feedback"] == []
        now += timedelta(days=1)
        app.state.daily_editions.clock = lambda: now
        client.portal.call(app.state.daily_editions.run_due)
        assert len(store.covers) == 3
        assert model.interpret.call_args.args[0]["profile"]["edition_feedback"] == feedback
        assert (client.get(path).json())["available"]
        assert not store.recent_edition_feedback("bob", now)
        now += timedelta(days=7)
        model.interpret.reset_mock()
        assert client.post("/v1/covers", json=forged).status_code == 200
        model.interpret.assert_not_awaited()


async def test_reason_can_drive_primary_needs_and_is_serializable_in_pipeline():
    model = ScriptedModel([finalize_first])
    model.interpret = AsyncMock(
        return_value=EditorialIntent.model_validate(
            {
                "needs": [
                    {
                        "topic": "Sciences",
                        "query": "astronomie sciences",
                        "priority": "secondary",
                        "level": "intermediate",
                        "evidence": "Davantage de sciences",
                    }
                ]
            }
        )
    )
    result = await pipeline(MemoryStore([article()]), model).run(
        request(
            edition_feedback=[
                {
                    "reason": "Davantage de sciences",
                    "created_at": at("2026-09-27T12:00:00+00:00"),
                }
            ]
        )
    )
    assert result.items
    intent = model.states[0]["editorial_intent"]
    assert next(n for n in intent["needs"] if n["topic"] == "Sciences")["priority"] == "primary"
    assert next(n for n in intent["needs"] if n["topic"] == "Python")["priority"] == "secondary"


def test_postgres_reservation_is_atomic_and_feedback_persists(pg_store):
    now = at("2026-09-27T12:00:00+00:00")
    day = now.astimezone(PARIS).date()
    cover = seed(pg_store)
    value = regeneration(cover)
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda _: pg_store.claim_regeneration("alice", day, value, now),
                range(2),
            )
        )
    assert sum(claim is not None for claim in claims) == 1
    pg_store.finish_regeneration(next(claim for claim in claims if claim), cover.id, now)
    assert pg_store.get_regeneration("alice", day)["status"] == "completed"
    # Reapplying the startup migration preserves both reservation and feedback.
    from importlib.resources import files

    with pg_store.pool.connection() as db:
        # Simulate the old deployed constraint before replaying the migration.
        db.execute(
            "ALTER TABLE edition_regenerations DROP CONSTRAINT edition_regenerations_reason_check"
        )
        db.execute(
            "ALTER TABLE edition_regenerations "
            "ADD CONSTRAINT edition_regenerations_reason_check "
            "CHECK(char_length(reason) BETWEEN 2 AND 1000)"
        )
        db.execute(files("broadwai").joinpath("schema.sql").read_text())
    assert not pg_store.claim_regeneration("alice", day, value, now)
    assert pg_store.recent_edition_feedback("alice", now)[0]["reason"] == value.reason
    assert not pg_store.recent_edition_feedback("bob", now)
    assert not pg_store.recent_edition_feedback("alice", now + timedelta(days=7))
    bob_cover = seed(pg_store, user="bob", now=now)
    assert pg_store.claim_regeneration("bob", day, regeneration(bob_cover), now)
    without_comment = RegenerationRequest(cover_id=cover.id)
    tomorrow = now + timedelta(days=1)
    assert pg_store.claim_regeneration("alice", day + timedelta(days=1), without_comment, tomorrow)
    assert not pg_store.claim_regeneration("alice", day + timedelta(days=1), value, tomorrow)
    assert [row["reason"] for row in pg_store.recent_edition_feedback("alice", tomorrow)] == [
        value.reason
    ]


def test_admin_reset_restores_one_attempt_without_generating_or_losing_feedback():
    store = MemoryStore()
    now = at("2026-09-27T12:00:00+00:00")
    cover = seed(store, now=now)
    seed(store, user="bob", now=now)
    app = create_app(
        Settings(_env_file=None, daily_editions_enabled=False), store=store, model=ScriptedModel()
    )
    with TestClient(app) as client:
        generate = AsyncMock(return_value=cover)
        app.state.regenerations.generate = generate
        app.state.regenerations.clock = lambda: now
        path = "/v1/readers/alice/regeneration"
        reset = "/v1/admin/readers/alice/regeneration/reset"
        payload = regeneration(cover).model_dump()
        assert client.post("/v1/admin/readers/missing/regeneration/reset").status_code == 404
        assert not client.post(reset).json()["reset"]
        assert client.post(path, json=payload).status_code == 200
        assert client.get(path).json()["can_reset"]
        feedback = store.recent_edition_feedback("alice", now)
        schedule = store.get_daily_profile("alice")
        assert client.post("/v1/admin/readers/bob/regeneration/reset").json()["reset"] is False
        assert not client.get(path).json()["available"]
        result = client.post(reset)
        assert result.status_code == 200
        assert result.json()["reset"] and result.json()["regeneration"]["available"]
        assert store.recent_edition_feedback("alice", now) == feedback
        assert store.get_daily_profile("alice") == schedule
        assert store.get_cover(cover.id) == cover
        generate.assert_awaited_once()  # Reset itself never generates a cover.
        assert not client.post(reset).json()["reset"]
        assert client.post(path, json={"cover_id": cover.id}).status_code == 200
        assert client.post(path, json={"cover_id": cover.id}).status_code == 409
        assert generate.await_count == 2
        dashboard = client.get("/v1/admin/editions").json()
        assert next(p for p in dashboard["profiles"] if p["user_id"] == "alice")["regeneration"][
            "can_reset"
        ]


async def test_progress_survives_reload_and_reset_refuses_an_active_attempt():
    store = MemoryStore()
    now = at("2026-09-27T12:00:00+00:00")
    cover = seed(store, now=now)
    service = Regenerations(store, AsyncMock(), asyncio.Lock(), clock=lambda: now)
    attempt = store.claim_regeneration("alice", now.date(), regeneration(cover), now, 90)
    now += timedelta(seconds=40)
    status = await service.status("alice")
    assert status["status"] == "running" and not status["can_reset"]
    assert status["elapsed_seconds"] == 40 and status["estimated_seconds"] == 90
    with pytest.raises(HTTPException) as exc:
        await service.reset("alice")
    assert exc.value.status_code == 409
    restarted = Regenerations(store, AsyncMock(), asyncio.Lock(), clock=lambda: now)
    assert await restarted.status("alice") == status
    store.finish_regeneration(attempt, cover.id, now)
    now += timedelta(seconds=20)
    assert (await restarted.status("alice"))["elapsed_seconds"] == 40
    assert store.estimate_regeneration_seconds("alice") == 40


def test_postgres_admin_resets_keep_history_and_one_active_attempt(pg_store):
    now = at("2026-09-27T12:00:00+00:00")
    day = now.date()
    cover = seed(pg_store, now=now)
    value = regeneration(cover)
    first = pg_store.claim_regeneration("alice", day, value, now)
    with pytest.raises(ValueError, match="en cours"):
        pg_store.reset_regeneration("alice", day, now)
    pg_store.finish_regeneration(first, cover.id, now + timedelta(seconds=80))
    assert pg_store.estimate_regeneration_seconds("alice") == 80
    assert pg_store.estimate_regeneration_seconds("bob") == 120
    now += timedelta(seconds=90)
    with ThreadPoolExecutor(max_workers=2) as executor:
        resets = list(
            executor.map(lambda _: pg_store.reset_regeneration("alice", day, now), range(2))
        )
    assert sum(resets) == 1
    assert pg_store.get_regeneration("alice", day) is None
    assert pg_store.recent_edition_feedback("alice", now)[0]["reason"] == value.reason
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(lambda _: pg_store.claim_regeneration("alice", day, value, now), range(2))
        )
    assert sum(claim is not None for claim in claims) == 1
    second = next(claim for claim in claims if claim)
    assert second != first
    # A crashed attempt can be reset after the server's stale-run grace period.
    now += timedelta(minutes=11)
    assert pg_store.reset_regeneration("alice", day, now)
    third = pg_store.claim_regeneration("alice", day, value, now)
    pg_store.finish_regeneration(second, cover.id, now)  # Late callback cannot finish third.
    assert pg_store.get_regeneration("alice", day)["id"] == third
    assert pg_store.get_regeneration("alice", day)["status"] == "running"
    assert len(pg_store.recent_edition_feedback("alice", now)) == 3
    from importlib.resources import files

    with pg_store.pool.connection() as db:
        db.execute(files("broadwai").joinpath("schema.sql").read_text())
    assert not pg_store.claim_regeneration("alice", day, value, now)
    assert len(pg_store.recent_edition_feedback("alice", now)) == 3


def test_legacy_daily_receipt_migrates_without_losing_allowance_or_feedback(pg_store):
    from importlib.resources import files

    now = at("2026-09-27T12:00:00+00:00")
    cover = seed(pg_store, now=now)
    value = regeneration(cover)
    receipt = pg_store.claim_regeneration("alice", now.date(), value, now)
    pg_store.finish_regeneration(receipt, cover.id, now)
    with pg_store.pool.connection() as db:
        db.execute("DROP INDEX edition_regenerations_daily_allowance")
        db.execute("ALTER TABLE edition_regenerations DROP CONSTRAINT edition_regenerations_pkey")
        db.execute(
            "ALTER TABLE edition_regenerations DROP COLUMN id, DROP COLUMN reset_at, "
            "DROP COLUMN finished_at, DROP COLUMN estimated_seconds"
        )
        db.execute("ALTER TABLE edition_regenerations ADD PRIMARY KEY(user_id,regeneration_date)")
        db.execute(files("broadwai").joinpath("schema.sql").read_text())
    assert pg_store.get_regeneration("alice", now.date())["status"] == "completed"
    assert not pg_store.claim_regeneration("alice", now.date(), value, now)
    assert pg_store.recent_edition_feedback("alice", now)[0]["reason"] == value.reason
    assert pg_store.reset_regeneration("alice", now.date(), now)
    assert pg_store.claim_regeneration("alice", now.date(), value, now)
