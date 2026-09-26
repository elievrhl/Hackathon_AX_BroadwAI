from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.models import Cover
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)


def test_api_cover_feedback_and_readback():
    source = article().model_copy(update={"text": "Python " * 801})
    store = MemoryStore([source])
    app = create_app(
        Settings(_env_file=None),
        store=store,
        model=ScriptedModel([finalize_first]),
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        response = client.post(
            "/v1/covers",
            json={
                "profile": {"user_id": "alice", "interests": [{"topic": "Python"}]},
                "size": 1,
            },
        )
        assert response.status_code == 200
        cover = response.json()
        assert cover["status"] == "complete"
        assert cover["items"][0]["reading_time_minutes"] == 5
        assert client.get(f"/v1/covers/{cover['id']}").json() == cover

        # Saved editions without the new field get an estimate without regeneration.
        legacy = Cover.model_validate(
            {
                **cover,
                "items": [
                    {key: value for key, value in item.items() if key != "reading_time_minutes"}
                    for item in cover["items"]
                ],
            }
        )
        store.put_cover(legacy)
        assert client.get(f"/v1/covers/{cover['id']}").json() == cover
        assert legacy.items[0].reading_time_minutes is None

        # Excerpts and unavailable articles must not yield a misleading full reading time.
        store.put_article(source.model_copy(update={"extraction_status": "excerpt"}))
        assert (
            client.get(f"/v1/covers/{cover['id']}").json()["items"][0]["reading_time_minutes"]
            is None
        )
        store.rows.clear()
        assert (
            client.get(f"/v1/covers/{cover['id']}").json()["items"][0]["reading_time_minutes"]
            is None
        )
        store.put_article(source)
        payload = {
            "user_id": "alice",
            "cover_id": cover["id"],
            "article_id": cover["items"][0]["article_id"],
            "kind": "useful",
        }
        assert client.post("/v1/feedback", json=payload).status_code == 201
        payload["user_id"] = "bob"
        assert client.post("/v1/feedback", json=payload).status_code == 422
        assert "text" not in client.get("/v1/articles").json()[0]


def test_missing_llm_configuration_never_silently_simulates_an_agent():
    settings = Settings(_env_file=None, openai_api_key=None, summary_model="", editor_model="")
    app = create_app(settings, store=MemoryStore())
    with TestClient(app) as client:
        response = client.post(
            "/v1/covers",
            json={"profile": {"user_id": "alice", "interests": [{"topic": "Python"}]}},
        )
        assert response.status_code == 503
        assert client.post("/v1/ingest", json={}).status_code == 422
        assert client.get("/v1/covers/unknown").status_code == 404
