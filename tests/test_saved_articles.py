from importlib.resources import files

from broadwai.collections import CollectionInput, Collections
from tests.fakes import ScriptedModel, article, finalize_first
from tests.test_collections import client_for
from tests.test_pipeline import pipeline, request


def test_one_click_bookmarks_are_idempotent_and_isolated(pg_store):
    source = article()
    pg_store.put_article(source)
    path = f"/v1/saved-articles/{source.id}"
    alice, bob = {"user_id": "alice"}, {"user_id": "bob"}
    with client_for(pg_store) as client:
        for _ in range(2):
            response = client.put(path, params=alice, json={})
            assert response.status_code == 200
            assert response.json()["article_ids"] == [source.id]
        assert client.get("/v1/collections", params=alice).json() == []
        assert client.get("/v1/saved-articles", params=bob).json()["items"] == []
        client.delete(path, params=bob)
        assert (
            client.get("/v1/saved-articles", params=alice).json()["items"][0]["url"] == source.url
        )
        assert client.put("/v1/saved-articles/missing", params=alice, json={}).status_code == 404
        assert client.get("/v1/saved-articles").status_code == 422
    # Reopening the app preserves the bookmark; repeated removal is harmless.
    with client_for(pg_store) as client:
        assert client.get("/v1/saved-articles", params=alice).json()["article_ids"] == [source.id]
        for _ in range(2):
            assert client.delete(path, params=alice).json()["items"] == []
        assert pg_store.get_article(source.id) is not None


def test_collections_organize_saved_articles_without_owning_them(pg_store):
    source = article()
    pg_store.put_article(source)
    repo = Collections(pg_store)
    first = repo.create("alice", CollectionInput(name="Sciences"))
    second = repo.create("alice", CollectionInput(name="À lire"))
    bob = repo.create("bob", CollectionInput(name="Bob"))
    repo.add("alice", first["id"], source.id)
    repo.add("alice", second["id"], source.id)
    repo.add("bob", bob["id"], source.id)
    assert repo.saved("alice")["article_ids"] == [source.id]
    repo.remove("alice", first["id"], source.id)
    repo.delete("alice", first["id"])
    assert repo.saved("alice")["article_ids"] == [source.id]
    repo.unsave("alice", source.id)
    assert repo.get("alice", second["id"])["article_ids"] == []
    assert repo.get("bob", bob["id"])["article_ids"] == [source.id]
    assert repo.saved("bob")["article_ids"] == [source.id]
    repo.save("alice", source.id)
    repo.add("alice", second["id"], source.id)
    repo.delete("alice", second["id"])
    assert repo.saved("alice")["article_ids"] == [source.id]


async def test_archives_include_all_editions_without_bookmarking_articles(pg_store):
    pg_store.put_article(article())
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    with client_for(pg_store) as client:
        rows = client.get("/v1/archives", params={"user_id": "alice"}).json()
        assert [row["id"] for row in rows] == [cover.id]
        assert rows[0]["artwork"]["sections"]
        assert client.get("/v1/archives", params={"user_id": "bob"}).json() == []
        assert client.get("/v1/archives").status_code == 422
        assert client.get("/v1/saved-articles", params={"user_id": "alice"}).json()["items"] == []
        path = f"/v1/saved-articles/{cover.items[0].article_id}"
        assert (
            client.put(path, params={"user_id": "bob"}, json={"cover_id": cover.id}).status_code
            == 404
        )
        data = client.put(path, params={"user_id": "alice"}, json={"cover_id": cover.id}).json()
        assert data["items"][0]["cover_id"] == cover.id
        client.delete(path, params={"user_id": "alice"})
        assert client.get("/v1/archives", params={"user_id": "alice"}).json() == rows


def test_existing_collections_migrate_once_and_removed_bookmarks_stay_removed(pg_store):
    source = article()
    pg_store.put_article(source)
    repo = Collections(pg_store)
    collection = repo.create("alice", CollectionInput(name="Anciennes lectures"))
    repo.add("alice", collection["id"], source.id)
    schema = files("broadwai").joinpath("schema.sql").read_text(encoding="utf-8")
    with pg_store.pool.connection() as db:
        db.execute("DELETE FROM saved_articles")
        db.execute("DELETE FROM reader_data_migrations WHERE id='saved-articles-v1'")
        db.execute(schema)
        db.execute(schema)
    assert repo.saved("alice")["article_ids"] == [source.id]
    repo.unsave("alice", source.id)
    with pg_store.pool.connection() as db:
        db.execute(schema)
    assert repo.saved("alice")["items"] == []
    assert repo.get("alice", collection["id"])["items"] == []


def test_bookmark_snapshot_survives_catalog_removal_and_can_be_organized(pg_store):
    source = article()
    pg_store.put_article(source)
    repo = Collections(pg_store)
    repo.save("alice", source.id)
    with pg_store.pool.connection() as db:
        db.execute("DELETE FROM articles WHERE id=%s", (source.id,))
    collection = repo.create("alice", CollectionInput(name="À relire"))
    result = repo.add("alice", collection["id"], source.id)
    assert result["items"][0]["url"] == source.url
    assert repo.saved("alice")["items"][0]["url"] == source.url
