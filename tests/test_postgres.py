import os
from importlib.resources import files
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from broadwai.models import ArticleImage, Feedback, PreferenceCreate, PreferenceUpdate, utcnow
from broadwai.preferences import PreferenceConflict
from broadwai.reader_chat import preference_snapshot
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


def test_library_api_persistence_isolation_and_removal(pg_store):
    from fastapi.testclient import TestClient

    from broadwai.api import create_app
    from broadwai.config import Settings
    from broadwai.models import Cover

    cover = Cover(
        user_id="alice",
        title="Une à conserver",
        status="partial",
        items=[],
        trace=[],
        warnings=[],
        usage={},
    )
    pg_store.put_cover(cover)
    bob = cover.model_copy(update={"id": uuid4().hex, "user_id": "bob"})
    pg_store.put_cover(bob)
    settings = Settings(_env_file=None, openai_api_key=None, summary_model="", editor_model="")
    with TestClient(create_app(settings, store=pg_store)) as client:
        path = f"/v1/library/{cover.id}"
        assert client.get("/v1/library", params={"user_id": "alice"}).json() == []
        assert client.put(path, params={"user_id": "bob"}).status_code == 404
        assert client.put(path).status_code == 422
        for _ in range(2):
            assert client.put(path, params={"user_id": "alice"}).json() == {"saved": True}
        saved = client.get("/v1/library", params={"user_id": "alice"}).json()
        assert len(saved) == 1
        assert saved[0]["id"] == cover.id
        assert saved[0]["artwork"]["version"] == 1
        assert saved[0]["saved_at"]
        assert pg_store.library("alice")[0]["artwork"] == saved[0]["artwork"]
        assert client.get("/v1/library", params={"user_id": "bob"}).json() == []
        assert client.get(f"/v1/covers/{cover.id}", params={"user_id": "bob"}).status_code == 404
        assert client.get(f"/v1/covers/{cover.id}", params={"user_id": "alice"}).status_code == 200
        assert [c["id"] for c in client.get("/v1/covers", params={"user_id": "bob"}).json()] == [
            bob.id
        ]
        client.delete(path, params={"user_id": "bob"})
        assert len(pg_store.library("alice")) == 1
        client.delete(path, params={"user_id": "alice"})
        assert pg_store.library("alice") == []
        assert pg_store.get_cover(cover.id) == cover


async def test_library_uses_images_discovered_after_generation(pg_store):
    source = article()
    pg_store.put_article(source)
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    pg_store.set_article_image(
        source.id, ArticleImage(url="https://example.com/photo.jpg", alt="Photo"), utcnow()
    )
    pg_store.save_edition("alice", cover.id)
    first = pg_store.library("alice")[0]
    assert first["artwork"]["photos"] == [source.id]
    pg_store.set_article_image(source.id, None, utcnow())
    pg_store.save_edition("alice", cover.id)
    assert pg_store.library("alice")[0] == first  # Repeated save preserves the recipe and date.
    pg_store.remove_edition("alice", cover.id)
    pg_store.save_edition("alice", cover.id)
    assert pg_store.library("alice")[0]["artwork"]["photos"] == []


async def test_likes_persist_are_idempotent_and_reversible(pg_store):
    from broadwai.reader_memory import ArticleLike

    pg_store.put_article(article())
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    event = ArticleLike(
        user_id="alice", cover_id=cover.id, article_id=cover.items[0].article_id, liked=True
    )
    pg_store.set_like(event)
    pg_store.set_like(event)
    assert pg_store.liked_ids("alice") == [event.article_id]
    assert pg_store.reading_memory("alice")["liked_articles_count"] == 1
    assert pg_store.reading_memory("bob")["liked_articles_count"] == 0
    assert event.article_id in pg_store.consumed_ids("alice")
    with pytest.raises(ValueError):
        pg_store.set_like(event.model_copy(update={"user_id": "bob"}))
    pg_store.set_like(event.model_copy(update={"liked": False}))
    assert pg_store.liked_ids("alice") == []
    assert pg_store.reading_memory("alice")["topics"] == []


def test_postgres_upsert_preserves_extracted_text(pg_store):
    full = article()
    pg_store.put_article(full)
    pg_store.put_article(full.model_copy(update={"text": "", "extraction_status": "excerpt"}))
    assert pg_store.get_article(full.id).text == full.text
    assert pg_store.stats()["articles"] == 1
    assert pg_store.articles()[0].id == full.id


def test_postgres_chat_atomic_persistence_replay_and_race(pg_store):
    from broadwai.reader_chat import ReaderChange
    from tests.test_reader_chat import message, reply

    request = message()
    plan = reply()
    first = pg_store.save_reader_message("alice", request, plan, [], {})
    assert pg_store.get_reader_message("alice", request.id) == first
    assert pg_store.list_reader_messages("alice") == [first]
    assert pg_store.list_reader_messages("bob") == []
    assert pg_store.save_reader_message("alice", request, plan, [], {}) == first
    rows = pg_store.list_preferences("alice", active_only=True)
    assert len(rows) == 1
    snapshot = preference_snapshot(rows)
    invalid = reply(id_=rows[0].id, action="less")
    invalid.changes.append(ReaderChange(preference_id="unknown-id", preference=None))
    with pytest.raises(ValueError):
        pg_store.save_reader_message("alice", message(), invalid, snapshot, {})
    assert pg_store.list_preferences("alice", active_only=True) == rows
    assert len(pg_store.list_reader_messages("alice")) == 1
    changed = pg_store.save_reader_message(
        "alice",
        message("Moins finalement"),
        reply(id_=rows[0].id, action="less"),
        snapshot,
        {},
    )
    assert changed["changes"][0]["kind"] == "updated"
    with pytest.raises(PreferenceConflict):
        pg_store.save_reader_message("alice", message(), plan, snapshot, {})
    assert pg_store.list_preferences("alice", active_only=True)[0].action == "less"


async def test_postgres_reader_preference_lifecycle_and_feedback_are_persistent(pg_store):
    value = PreferenceCreate(action="more", target_kind="topic", target="Python", scope="next")
    first = pg_store.create_preference("alice", value)
    assert pg_store.create_preference("alice", value).id == first.id
    assert pg_store.list_preferences("bob") == []
    with pytest.raises(PreferenceConflict):
        pg_store.create_preference("bob", value)
    corrected = pg_store.update_preference(
        "alice",
        first.id,
        PreferenceUpdate(
            **value.model_dump(exclude={"id", "explanation"}),
            explanation="Les articles approfondis",
            revision=1,
        ),
    )
    with pytest.raises(PreferenceConflict):
        pg_store.update_preference("alice", first.id, revision=1)
    assert pg_store.list_preferences("alice")[0] == corrected
    item = article()
    pg_store.put_article(item)
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    applied = pg_store.list_preferences("alice")[0]
    assert applied.status == "applied" and applied.applied_cover_id == cover.id
    linked = PreferenceCreate(action="less", target_kind="content_type", target="analysis")
    event = Feedback(
        user_id="alice",
        cover_id=cover.id,
        article_id=item.id,
        kind="not_interested",
        comment="Trop de lectures de ce format",
        reason="style",
        preference=linked,
    )
    rule = pg_store.add_feedback(event)
    pg_store.add_feedback(event)
    assert len(pg_store.list_preferences("alice", active_only=True)) == 1
    assert pg_store.feedback_for_cover("alice", cover.id)[0]["comment"] == event.comment
    pg_store.update_preference("alice", rule.id, revision=1)
    pg_store.add_feedback(event)
    assert pg_store.list_preferences("alice", active_only=True) == []
    # Schema migration is additive and repeatable with existing events and editions.
    with pg_store.pool.connection() as db:
        db.execute(files("broadwai").joinpath("schema.sql").read_text(encoding="utf-8"))
    assert pg_store.get_cover(cover.id).id == cover.id
    assert pg_store.feedback_for_cover("alice", cover.id)[0]["preference_id"] == linked.id


async def test_postgres_preference_concurrent_correction_and_feedback_atomicity(
    pg_store,
):
    value = PreferenceCreate(
        action="diversify", target_kind="topic", target="Histoire", scope="next"
    )
    first = pg_store.create_preference("alice", value)
    item = article()
    pg_store.put_article(item)

    class CorrectingModel(ScriptedModel):
        async def decide(self, state, budget):
            pg_store.update_preference(
                "alice", first.id, PreferenceUpdate(**value.model_dump(exclude={"id"}), revision=1)
            )
            return finalize_first(state)

    cover = await pipeline(pg_store, CorrectingModel(), max_agent_steps=1).run(request())
    assert pg_store.list_preferences("alice", active_only=True)[0].revision == 2
    bad = Feedback(
        user_id="bob",
        cover_id=cover.id,
        article_id=item.id,
        kind="not_interested",
        preference=value,
    )
    with pytest.raises(ValueError):
        pg_store.add_feedback(bad)
    assert pg_store.list_preferences("bob") == []
    replacement = pg_store.create_preference(
        "alice", PreferenceCreate(action="exclude", target_kind="topic", target="histoire")
    )
    assert pg_store.list_preferences("alice", active_only=True) == [replacement]


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


async def test_postgres_image_enrichment_preserves_text_and_cached_brief(pg_store):
    item = article()
    pg_store.put_article(item)
    model = ScriptedModel([finalize_first])
    await pipeline(pg_store, model).run(request())
    cached = pg_store.get_brief(item, model.summary_version)
    picture = ArticleImage(url="https://cdn.example/article.jpg", alt="Illustration originale")
    checked_at = utcnow()
    pg_store.set_article_image(item.id, picture, checked_at)
    stored = pg_store.get_article(item.id)
    assert stored.image == picture and stored.image_checked_at == checked_at
    assert stored.text == item.text and stored.content_hash == item.content_hash
    assert pg_store.get_brief(stored, model.summary_version) == cached


def test_postgres_image_review_claim_and_persistent_verdict(pg_store):
    from concurrent.futures import ThreadPoolExecutor

    item = article()
    pg_store.put_article(item)
    assert not pg_store.article_has_cover(item.id)
    metadata = {"model": "gpt-5.4-nano", "image_bytes": 30_000}
    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(
            executor.map(
                lambda claim: pg_store.claim_image_review("key", item.id, claim, metadata),
                ["worker-a", "worker-b"],
            )
        )
    assert sorted(claims) == [False, True]
    winner = "worker-a" if claims[0] else "worker-b"
    loser = "worker-b" if claims[0] else "worker-a"
    pg_store.finish_image_review("key", loser, {"verdict": "keep"})
    assert pg_store.get_image_review("key")["status"] == "pending"
    pg_store.finish_image_review(
        "key", winner, {"verdict": "reject", "usage": {"output_tokens": 7}}
    )
    assert pg_store.get_image_review("key")["verdict"] == "reject"
    assert not pg_store.claim_image_review("key", item.id, "worker-c", metadata)
    assert pg_store.get_article(item.id) == item
    assert pg_store.claim_image_review("error-key", item.id, "worker-a", metadata)
    pg_store.finish_image_review(
        "error-key", "worker-a", {"verdict": "uncertain", "error": "Timeout"}
    )
    assert not pg_store.claim_image_review("error-key", item.id, "worker-b", metadata)
    with pg_store.pool.connection() as db:
        db.execute(
            "UPDATE image_reviews SET retry_after=now() - interval '1 second' "
            "WHERE cache_key='error-key'"
        )
    assert pg_store.claim_image_review("error-key", item.id, "worker-b", metadata)
    assert pg_store.get_image_review("error-key")["previous_attempts"][0]["error"] == "Timeout"


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
