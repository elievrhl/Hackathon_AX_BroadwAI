from importlib.resources import files

from tests.client import TestClient

from broadwai.api import create_app
from broadwai.collections import CollectionInput, Collections
from broadwai.config import Settings
from tests.fakes import ScriptedModel, article, finalize_first
from tests.test_pipeline import pipeline, request


def client_for(store):
    return TestClient(create_app(Settings(_env_file=None, openai_api_key=None), store=store))


def test_collections_crud_membership_and_account_isolation(pg_store):
    source = article()
    pg_store.put_article(source)
    alice = {"user_id": "alice"}
    bob = {"user_id": "bob"}
    with client_for(pg_store) as client:
        assert client.post("/v1/collections", params=alice, json={"name": " "}).status_code == 422
        first = client.post("/v1/collections", params=alice, json={"name": "Sciences"}).json()
        second = client.post("/v1/collections", params=alice, json={"name": "À lire"}).json()
        path = f"/v1/collections/{first['id']}"
        member = f"{path}/articles/{source.id}"
        assert client.get("/v1/collections", params=bob).json() == []
        assert client.get(path, params=bob).status_code == 404
        assert client.patch(path, params=bob, json={"name": "Stolen"}).status_code == 404
        assert client.delete(path, params=bob).status_code == 404
        assert client.put(member, params=bob, json={}).status_code == 404
        for _ in range(2):
            added = client.put(member, params=alice, json={}).json()
            assert added["item_count"] == 1
        assert added["items"][0]["title"] == source.title
        assert added["article_ids"] == [source.id]
        assert client.delete(member, params=bob).status_code == 404
        assert client.put(f"{path}/articles/missing", params=alice, json={}).status_code == 404
        other_path = f"/v1/collections/{second['id']}"
        client.put(f"{other_path}/articles/{source.id}", params=alice, json={})
        renamed = client.patch(
            path,
            params=alice,
            json={
                "name": "Science et société",
                "description": "Les idées à approfondir",
            },
        ).json()
        assert renamed["name"] == "Science et société"
        assert renamed["artwork"]["palette"] == first["artwork"]["palette"]
        assert client.delete(member, params=alice).json()["item_count"] == 0
        assert client.get(other_path, params=alice).json()["item_count"] == 1
        assert client.delete(path, params=alice).status_code == 200
        assert len(client.get("/v1/collections", params=alice).json()) == 1
        assert pg_store.get_article(source.id) is not None
        assert client.get(other_path, params=alice).json()["items"][0]["url"] == source.url


async def test_collection_preserves_cover_origin_and_refuses_other_readers_cover(pg_store):
    pg_store.put_article(article())
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    repo = Collections(pg_store)
    collection = repo.create("alice", CollectionInput(name="Mes lectures"))
    with client_for(pg_store) as client:
        path = f"/v1/collections/{collection['id']}/articles/{cover.items[0].article_id}"
        data = client.put(path, params={"user_id": "alice"}, json={"cover_id": cover.id}).json()
        assert data["items"][0]["cover_id"] == cover.id
        bob = repo.create("bob", CollectionInput(name="Autres lectures"))
        path = f"/v1/collections/{bob['id']}/articles/{cover.items[0].article_id}"
        assert (
            client.put(path, params={"user_id": "bob"}, json={"cover_id": cover.id}).status_code
            == 404
        )
    # An article remains readable even if it is later removed from the live catalog.
    with pg_store.pool.connection() as db:
        db.execute("DELETE FROM articles WHERE id=%s", (cover.items[0].article_id,))
    assert repo.get("alice", collection["id"])["items"][0]["url"] == cover.items[0].url


async def test_saved_editions_migrate_once_without_resurrecting_deleted_collections(pg_store):
    pg_store.put_article(article())
    cover = await pipeline(pg_store, ScriptedModel([finalize_first])).run(request())
    pg_store.save_edition("alice", cover.id)
    schema = files("broadwai").joinpath("schema.sql").read_text(encoding="utf-8")
    with pg_store.pool.connection() as db:
        db.execute(schema)
        db.execute(schema)
    repo = Collections(pg_store)
    rows = repo.list("alice")
    assert len(rows) == 1
    assert rows[0]["name"] == cover.title
    assert rows[0]["article_ids"] == [cover.items[0].article_id]
    assert repo.get("alice", rows[0]["id"])["items"][0]["cover_id"] == cover.id
    repo.remove("alice", rows[0]["id"], cover.items[0].article_id)
    with pg_store.pool.connection() as db:
        db.execute(schema)
    assert repo.get("alice", rows[0]["id"])["item_count"] == 0
    repo.delete("alice", rows[0]["id"])
    with pg_store.pool.connection() as db:
        db.execute(schema)
    assert repo.list("alice") == []
    assert pg_store.get_cover(cover.id) is not None


def test_browser_bookmarks_import_is_idempotent_and_survives_reopening(pg_store):
    source = article()
    pg_store.put_article(source)
    with client_for(pg_store) as client:
        for _ in range(2):
            result = client.post(
                "/v1/collections/import-bookmarks",
                params={"user_id": "alice"},
                json={"article_ids": [source.id, source.id, "missing"]},
            )
            assert result.json()["imported_ids"] == [source.id]
    with client_for(pg_store) as client:
        rows = client.get("/v1/collections", params={"user_id": "alice"}).json()
        assert len(rows) == 1 and rows[0]["name"] == "À lire"
        assert rows[0]["item_count"] == 1
        assert client.get("/v1/collections", params={"user_id": "bob"}).json() == []
