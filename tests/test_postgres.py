import os
from importlib.resources import files
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from broadwai.models import Feedback
from broadwai.store import Store
from tests.fakes import ScriptedModel, article, finalize_first
from tests.test_pipeline import pipeline, request


@pytest.fixture
def pg_store():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL requis pour les tests PostgreSQL réels")
    schema = "test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = Store(make_conninfo(url, options=f"-c search_path={schema}"))
    try:
        store.open()
        yield store
    finally:
        store.close()
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_upsert_preserves_extracted_text(pg_store):
    full = article()
    pg_store.put_article(full)
    pg_store.put_article(full.model_copy(update={"text": "", "extraction_status": "excerpt"}))
    assert pg_store.get_article(full.id).text == full.text
    assert pg_store.stats()["articles"] == 1
    assert pg_store.articles()[0].id == full.id


def test_postgres_website_upgrade_preserves_existing_sources_and_proposals(pg_store):
    from broadwai.sources import SourceInput

    data = SourceInput(name="Flux existant", url="https://example.com/feed").model_dump()
    source = pg_store.save_source(data)
    proposal = pg_store.propose_source("https://other.example/feed", "Autre", "Utile", data["url"])
    # Reconstruct the pre-website schema and apply the actual startup upgrade twice.
    with pg_store.pool.connection() as db:
        db.execute("ALTER TABLE source_proposals DROP COLUMN kind")
        db.execute("ALTER TABLE sources DROP CONSTRAINT sources_kind_check")
        db.execute(
            "ALTER TABLE sources ADD CONSTRAINT sources_kind_check "
            "CHECK (kind IN ('rss', 'hacker_news'))"
        )
        schema = files("broadwai").joinpath("schema.sql").read_text(encoding="utf-8")
        db.execute(schema)
        db.execute(schema)
    assert pg_store.list_sources()[0]["id"] == source["id"]
    assert pg_store.list_proposals()[0]["id"] == proposal["id"]
    assert pg_store.list_proposals()[0]["kind"] == "rss"
    website = pg_store.save_source({**data, "kind": "website", "url": "https://example.com/blog"})
    assert website["kind"] == "website"


async def test_postgres_complete_pipeline_cache_and_feedback(pg_store):
    item = article()
    pg_store.put_article(item)
    model = ScriptedModel([finalize_first, finalize_first])
    cover = await pipeline(pg_store, model).run(request())
    cached = await pipeline(pg_store, model).run(request())
    assert cached.usage["summary_cache_hits"] == 1
    assert pg_store.get_cover(cover.id) == cover
    history = pg_store.list_covers(limit=1)
    assert history[0]["id"] == cached.id
    assert history[0]["audit_version"] == "1"
    assert pg_store.get_cover(cover.id).diagnostics["events"]
    event = Feedback(user_id="alice", cover_id=cover.id, article_id=item.id, kind="useful")
    pg_store.add_feedback(event)
    pg_store.add_feedback(event)
    assert pg_store.consumed_ids("alice") == {item.id}
    assert pg_store.consumed_ids("bob") == set()
    with pytest.raises(ValueError):
        pg_store.add_feedback(event.model_copy(update={"user_id": "bob"}))


async def test_postgres_content_change_invalidates_brief(pg_store):
    item = article()
    pg_store.put_article(item)
    model = ScriptedModel([finalize_first, finalize_first])
    await pipeline(pg_store, model).run(request())
    updated = item.model_copy(update={"text": item.text + " Mise à jour du contenu."})
    pg_store.put_article(updated)
    assert pg_store.get_brief(updated, model.summary_version) is None
    await pipeline(pg_store, model).run(request())
    assert model.summary_calls == 2


def test_postgres_sources_collection_and_article_browsing(pg_store):
    from broadwai.sources import SourceInput

    item = article()
    pg_store.put_article(item)
    data = SourceInput(name="Python", url="https://example.com/feed").model_dump()
    source = pg_store.save_source(data)
    with pytest.raises(ValueError):
        pg_store.save_source(data)
    report = {"article_ids": [item.id], "collected": 1, "errors": []}
    pg_store.record_collection(source["id"], report)
    pg_store.record_collection(source["id"], report)
    assert pg_store.list_sources()[0]["article_count"] == 1
    assert pg_store.browse_articles(source_id=source["id"])["total"] == 1
    assert pg_store.browse_articles(q="Python", status="extracted")["total"] == 1
    assert pg_store.browse_articles(q="%")["total"] == 0
    assert pg_store.browse_articles(offset=10)["items"] == []
    assert pg_store.article_detail(item.id)["sources"][0]["name"] == "Python"
    edited = pg_store.save_source({**data, "name": "Renommée", "enabled": False}, source["id"])
    assert edited["name"] == "Renommée" and not edited["enabled"]
    assert pg_store.delete_source(source["id"])
    assert pg_store.get_article(item.id)
    assert pg_store.article_detail(item.id)["sources"] == []


@pytest.mark.parametrize("kind", ["rss", "website"])
def test_postgres_proposals_require_review_and_approval_is_idempotent(pg_store, kind):
    from fastapi.testclient import TestClient

    from broadwai.api import create_app
    from broadwai.config import Settings

    proposal = pg_store.propose_source(
        "https://example.com/feed", "Example", "Pertinent", "https://example.com/", kind=kind
    )
    duplicate = pg_store.propose_source(
        "https://example.com/feed", "Other name", "Other reason", "https://example.com/", kind=kind
    )
    assert proposal["id"] == duplicate["id"]
    assert pg_store.list_sources() == []
    with TestClient(create_app(Settings(_env_file=None), store=pg_store)) as client:
        assert client.get("/v1/source-proposals").json()[0]["status"] == "proposed"
        route = f"/v1/source-proposals/{proposal['id']}/review"
        assert client.post(route, json={"approve": True}).json()["status"] == "approved"
        assert client.post(route, json={"approve": True}).status_code == 200
        assert (
            client.post("/v1/source-proposals/missing/review", json={"approve": True}).status_code
            == 404
        )
    assert len(pg_store.list_sources()) == 1
    assert pg_store.list_sources()[0]["enabled"]
    assert pg_store.list_sources()[0]["kind"] == kind
    rejected = pg_store.propose_source(
        "https://other.example/feed", "Other", "Pertinent", "https://other.example/"
    )
    assert pg_store.review_proposal(rejected["id"], False)["status"] == "rejected"
    assert pg_store.review_proposal(rejected["id"], True)["status"] == "rejected"
    assert len(pg_store.list_sources()) == 1
