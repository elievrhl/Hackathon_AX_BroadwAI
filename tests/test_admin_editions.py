from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.daily_editions import next_edition_at
from broadwai.models import utcnow
from tests.client import TestClient
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)
from tests.test_pipeline import request


def test_admin_dashboard_and_manual_generation_use_saved_profile_without_changing_schedule():
    store = MemoryStore([article()])
    # This reader was registered before the first-edition-on-signup behavior.
    now = utcnow()
    store.save_daily_profile(request(), next_edition_at(now), now)
    app = create_app(
        Settings(_env_file=None, openai_api_key="private-test-key"),
        store=store,
        model=ScriptedModel([finalize_first]),
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    with TestClient(app) as client:
        payload = request().model_dump(mode="json")
        # Seed a future schedule: first-time reader registration now prepares an edition.
        store.save_daily_profile(request(), next_edition_at(utcnow()), utcnow())
        before = client.get("/v1/readers/alice/daily-edition").json()
        dashboard = client.get("/v1/admin/editions")
        dashboard.raise_for_status()
        assert "private-test-key" not in dashboard.text
        data = dashboard.json()
        assert data["llm_configured"] and data["daily_editions_enabled"]
        assert not data["preparing"]
        assert data["profiles"][0]["request"] == payload
        assert data["profiles"][0]["schedule"]["next_run_at"] == before["next_run_at"]
        assert client.get("/v1/admin/editions?offset=1").json()["profiles"] == []
        assert client.get("/v1/admin/editions?limit=201").status_code == 422
        assert not store.covers  # Reading admin pages never generates an edition.
        response = client.post("/v1/admin/readers/alice/covers")
        assert response.status_code == 200
        cover = response.json()
        assert cover["user_id"] == "alice" and cover["items"]
        assert store.get_cover(cover["id"]) is not None
        assert client.get("/v1/covers?user_id=alice").json()[0]["id"] == cover["id"]
        assert client.get("/v1/covers?user_id=bob").json() == []
        after = client.get("/v1/readers/alice/daily-edition").json()
        assert after["next_run_at"] == before["next_run_at"]
        assert store.daily_runs == {}


def test_admin_generation_handles_missing_profile_model_and_inflight_work():
    store = MemoryStore()
    app = create_app(Settings(_env_file=None, openai_api_key=None), store=store)
    with TestClient(app) as client:
        assert client.post("/v1/admin/readers/missing/covers").status_code == 404
        client.put("/v1/readers/alice/daily-edition", json=request().model_dump(mode="json"))
        assert client.post("/v1/admin/readers/alice/covers").status_code == 503
        assert not client.get("/v1/admin/editions").json()["llm_configured"]
    app = create_app(
        Settings(_env_file=None, daily_editions_enabled=False),
        store=store,
        model=ScriptedModel(),
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    with TestClient(app) as client:
        client.portal.call(app.state.cover_lock.acquire)
        try:
            assert client.get("/v1/admin/editions").json()["preparing"]
            assert client.post("/v1/admin/readers/alice/covers").status_code == 429
        finally:
            client.portal.call(app.state.cover_lock.release)


def test_admin_profiles_read_back_current_postgres_settings(pg_store):
    from broadwai.daily_editions import next_edition_at
    from broadwai.models import utcnow

    now = utcnow()
    payload = request()
    pg_store.save_daily_profile(payload, next_edition_at(now), now)
    assert pg_store.get_daily_profile("alice") == payload.model_dump(mode="json")
    assert pg_store.get_daily_profile("unknown") is None
    assert pg_store.list_daily_profiles()[0]["user_id"] == "alice"
    assert pg_store.list_daily_profiles(offset=1) == []
