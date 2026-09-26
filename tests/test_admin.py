import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from tests.admin_fakes import AdminCollector, AdminStore
from tests.fakes import article

SOURCE = {
    "name": "Blog Python",
    "url": "https://example.com/feed",
    "kind": "rss",
    "enabled": True,
    "limit_per_source": 10,
}


@pytest.fixture
def admin():
    store = AdminStore()
    collector = AdminCollector(store)
    app = create_app(Settings(_env_file=None), store=store, collector=collector)
    with TestClient(app) as client:
        yield client, store, collector


def test_admin_page_and_assets_are_served_without_llm(admin):
    client, _, _ = admin
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Sources & articles" in response.text
    assert client.get("/").url.path == "/admin"
    assert client.get("/admin/assets/admin.js").status_code == 200
    assert client.get("/admin/assets/admin.css").status_code == 200


def test_source_edit_pause_duplicate_and_delete_preserves_articles(admin):
    client, store, _ = admin
    created = client.post("/v1/sources", json=SOURCE)
    assert created.status_code == 201
    source_id = created.json()["id"]
    assert client.post("/v1/sources", json=SOURCE).status_code == 409
    updated = client.put(
        f"/v1/sources/{source_id}", json={**SOURCE, "name": "Python modifié", "enabled": False}
    )
    assert updated.json()["enabled"] is False
    assert client.get("/v1/sources").json()[0]["name"] == "Python modifié"
    # Individual collection is permitted even if excluded from grouped collections.
    assert client.post(f"/v1/sources/{source_id}/collect").status_code == 200
    assert len(store.articles()) == 1
    assert client.delete(f"/v1/sources/{source_id}").status_code == 204
    assert client.get("/v1/sources").json() == []
    assert len(store.articles()) == 1


def test_collect_active_only_records_partial_failure_and_provenance(admin):
    client, store, collector = admin
    source = client.post("/v1/sources", json=SOURCE).json()
    client.post(
        "/v1/sources", json={**SOURCE, "name": "Broken", "url": "https://broken.example/rss"}
    )
    client.post(
        "/v1/sources",
        json={**SOURCE, "name": "Paused", "url": "https://paused.example/rss", "enabled": False},
    )
    response = client.post("/v1/sources/collect")
    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 2
    assert len(collector.calls) == 2
    assert sum(len(r["errors"]) for r in results) == 1
    sources = client.get("/v1/sources").json()
    saved = next(s for s in sources if s["id"] == source["id"])
    assert saved["last_collected_at"]
    assert saved["article_count"] == 1
    article_id = store.articles()[0].id
    detail = client.get(f"/v1/admin/articles/{article_id}").json()
    assert detail["sources"] == [{"id": source["id"], "name": source["name"]}]
    assert detail["article"]["excerpt"]


def test_pagination_filters_and_full_detail(admin):
    client, store, _ = admin
    for i in range(30):
        store.put_article(article(i, title=f"Document {i}", extracted=i % 2 == 0))
    page = client.get("/v1/admin/articles?limit=10&offset=20").json()
    assert page["total"] == 30 and len(page["items"]) == 10
    assert "text" not in page["items"][0]
    extracted = client.get("/v1/admin/articles?status=extracted").json()
    assert extracted["total"] == 15
    assert client.get("/v1/admin/articles?q=Document%2029").json()["total"] == 1
    item = article(0, title="Document 0")
    detail = client.get(f"/v1/admin/articles/{item.id}").json()
    assert detail["article"]["text"]
    assert detail["briefs"] == []
    assert client.get("/v1/admin/articles?source_id=unknown").json()["total"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"url": "http://127.0.0.1/feed"},
        {"url": "file:///test"},
        {"limit_per_source": 100},
        {"name": " "},
        {"kind": "other"},
    ],
)
def test_invalid_source_is_rejected(admin, changes):
    client, _, _ = admin
    assert client.post("/v1/sources", json={**SOURCE, **changes}).status_code == 422


def test_hacker_news_source_and_missing_ids(admin):
    client, _, collector = admin
    source = client.post("/v1/sources", json={"name": "HN", "kind": "hacker_news"}).json()
    client.post(f"/v1/sources/{source['id']}/collect")
    assert collector.calls[0].hacker_news
    assert collector.calls[0].feed_urls == []
    assert client.put("/v1/sources/missing", json=SOURCE).status_code == 404
    assert client.delete("/v1/sources/missing").status_code == 404
    assert client.post("/v1/sources/missing/collect").status_code == 404
    assert client.get("/v1/admin/articles/missing").status_code == 404
