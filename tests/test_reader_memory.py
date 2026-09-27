from tests.client import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.reader_memory import reading_memory
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    finalize_first,
)
from tests.test_pipeline import pipeline, request


def test_memory_uses_article_evidence_without_double_counting_topics():
    item = {
        "article_id": "a",
        "title": "Cyberpunk",
        "brief": {
            "topics": ["Cyberpunk", "cyberpunk", " Littérature "],
            "summary": "Une lecture.",
            "level": "expert",
            "content_type": "analysis",
        },
    }
    memory = reading_memory([item])
    assert memory["topics"] == [
        {"topic": "cyberpunk", "likes": 1},
        {"topic": "littérature", "likes": 1},
    ]
    assert memory["examples"][0]["article_id"] == "a"
    assert memory["reading_levels"] == {"expert": 1}
    assert reading_memory([])["topics"] == []


async def test_likes_api_and_generation_use_server_memory(monkeypatch):
    store = MemoryStore([article()])
    model = ScriptedModel([finalize_first])
    cover = await pipeline(store, model).run(request())
    app = create_app(
        Settings(_env_file=None),
        store=store,
        model=model,
        collector=FakeCollector(store),
        search=FakeSearch(),
    )
    captured = []

    async def run(self, req):
        captured.append(req.profile)
        return cover

    monkeypatch.setattr("broadwai.api.CoverPipeline.run", run)
    payload = {
        "user_id": "alice",
        "cover_id": cover.id,
        "article_id": cover.items[0].article_id,
        "liked": True,
    }
    with TestClient(app) as client:
        assert client.put("/v1/likes", json={**payload, "user_id": "bob"}).status_code == 422
        assert client.put("/v1/likes", json={**payload, "article_id": "absent"}).status_code == 422
        for _ in range(2):
            assert client.put("/v1/likes", json=payload).status_code == 200
        assert client.get("/v1/likes?user_id=alice").json()["article_ids"] == [
            payload["article_id"]
        ]
        assert client.get("/v1/likes?user_id=bob").json()["article_ids"] == []
        req = request().model_dump(mode="json")
        req["profile"]["reading_memory"] = {"topics": [{"topic": "forged", "likes": 100}]}
        assert client.post("/v1/covers", json=req).status_code == 200
        assert captured[0].reading_memory == store.reading_memory("alice")
        assert captured[0].reading_memory["liked_articles_count"] == 1
        assert captured[0].notes == req["profile"]["notes"]
        assert client.put("/v1/likes", json={**payload, "liked": False}).status_code == 200
        assert client.get("/v1/likes?user_id=alice").json()["article_ids"] == []
        assert store.reading_memory("alice")["topics"] == []
