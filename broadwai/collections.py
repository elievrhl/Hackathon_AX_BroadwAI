"""Personal article collections. Demo identities follow the existing local account model."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field

from broadwai.library import artwork
from broadwai.models import Article, Model

router = APIRouter(prefix="/v1/collections")


class CollectionInput(Model):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field("", max_length=600)


class AddArticle(Model):
    cover_id: str | None = Field(None, min_length=1, max_length=100)


class ImportBookmarks(Model):
    article_ids: list[str] = Field(max_length=2000)


class Collections:
    def __init__(self, store):
        self.store = store
        self.pool = store.pool

    @staticmethod
    def owned(db, user_id, collection_id, *, lock=False):
        row = db.execute(
            "SELECT * FROM article_collections WHERE id=%s AND user_id=%s"
            + (" FOR UPDATE" if lock else ""),
            (collection_id, user_id),
        ).fetchone()
        if row is None:
            raise ValueError("Collection introuvable pour ce compte")
        return row

    def list(self, user_id, collection_id=None):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT * FROM article_collections WHERE user_id=%s "
                + ("AND id=%s " if collection_id else "")
                + "ORDER BY updated_at DESC, id",
                (user_id, collection_id) if collection_id else (user_id,),
            ).fetchall()
            if collection_id and not rows:
                raise ValueError("Collection introuvable pour ce compte")
            members = (
                cur.execute(
                    "SELECT m.*, a.payload AS current_article FROM collection_articles m "
                    "LEFT JOIN articles a ON a.id=m.article_id "
                    "WHERE m.collection_id=ANY(%s) ORDER BY m.added_at DESC, m.article_id",
                    ([row["id"] for row in rows],),
                ).fetchall()
                if rows
                else []
            )
        grouped = {row["id"]: [] for row in rows}
        for member in members:
            item = {**member["payload"], "added_at": member["added_at"]}
            if member["current_article"]:
                article = Article.model_validate(member["current_article"])
                item.update(
                    title=article.title,
                    url=article.url,
                    source=article.source,
                    format=article.format,
                    media=article.media,
                    image=article.image.model_dump() if article.image else None,
                    image_checked=bool(article.image_checked_at),
                    reading_time_minutes=article.reading_time_minutes,
                )
            grouped[member["collection_id"]].append(item)
        result = []
        for row in rows:
            items = grouped[row["id"]]
            recipe = artwork(
                SimpleNamespace(
                    id=row["id"],
                    items=[
                        SimpleNamespace(
                            article_id=i["article_id"],
                            image=i.get("image"),
                            image_checked=i.get("image_checked", False),
                            section=i.get("section", ""),
                        )
                        for i in items
                    ],
                )
            )
            recipe["sections"] = [s for s in recipe["sections"] if s]
            data = {
                **{
                    key: row[key]
                    for key in ("id", "name", "description", "created_at", "updated_at")
                },
                "title": row["name"],
                "item_count": len(items),
                "article_ids": [i["article_id"] for i in items],
                "artwork": recipe,
            }
            if collection_id:
                data["items"] = items
            result.append(data)
        return result

    def get(self, user_id, collection_id):
        return self.list(user_id, collection_id)[0]

    def create(self, user_id, data):
        collection_id = uuid4().hex
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO article_collections (id,user_id,name,description) "
                "VALUES (%s,%s,%s,%s)",
                (collection_id, user_id, data.name, data.description),
            )
        return self.get(user_id, collection_id)

    def edit(self, user_id, collection_id, data):
        with self.pool.connection() as db:
            self.owned(db, user_id, collection_id, lock=True)
            db.execute(
                "UPDATE article_collections SET name=%s,description=%s,updated_at=now() "
                "WHERE id=%s",
                (data.name, data.description, collection_id),
            )
        return self.get(user_id, collection_id)

    def delete(self, user_id, collection_id):
        with self.pool.connection() as db:
            self.lock_reader(db, user_id)
            self.owned(db, user_id, collection_id, lock=True)
            db.execute("DELETE FROM article_collections WHERE id=%s", (collection_id,))

    def snapshot(self, user_id, article_id, cover_id=None):
        if cover_id:
            cover = self.store.get_cover(cover_id)
            if cover is None or cover.user_id != user_id:
                raise ValueError("Édition introuvable pour ce compte")
            item = next((i for i in cover.items if i.article_id == article_id), None)
            if item is None:
                raise ValueError("Article absent de cette édition")
            return {**item.model_dump(mode="json"), "cover_id": cover_id}
        article = self.store.get_article(article_id)
        if article is None:
            with self.pool.connection() as db:
                row = db.execute(
                    "SELECT payload FROM saved_articles WHERE user_id=%s AND article_id=%s",
                    (user_id, article_id),
                ).fetchone()
            if row:
                return row[0]
            raise ValueError("Article introuvable")
        return {
            "article_id": article.id,
            "title": article.title,
            "url": article.url,
            "source": article.source,
            "format": article.format,
            "media": article.media,
            "published_at": article.published_at.isoformat() if article.published_at else None,
            "section": "",
            "image": article.image.model_dump() if article.image else None,
            "image_checked": bool(article.image_checked_at),
            "reading_time_minutes": article.reading_time_minutes,
        }

    @staticmethod
    def insert_member(db, collection_id, article_id, payload):
        row = db.execute(
            "INSERT INTO collection_articles (collection_id,article_id,payload) VALUES (%s,%s,%s) "
            "ON CONFLICT DO NOTHING RETURNING article_id",
            (collection_id, article_id, Jsonb(payload)),
        ).fetchone()
        if row:
            db.execute(
                "UPDATE article_collections SET updated_at=now() WHERE id=%s", (collection_id,)
            )

    def add(self, user_id, collection_id, article_id, cover_id=None):
        payload = self.snapshot(user_id, article_id, cover_id)
        with self.pool.connection() as db:
            self.lock_reader(db, user_id)
            self.owned(db, user_id, collection_id, lock=True)
            self.insert_saved(db, user_id, article_id, payload)
            self.insert_member(db, collection_id, article_id, payload)
        return self.get(user_id, collection_id)

    def remove(self, user_id, collection_id, article_id):
        with self.pool.connection() as db:
            self.lock_reader(db, user_id)
            self.owned(db, user_id, collection_id, lock=True)
            row = db.execute(
                "DELETE FROM collection_articles WHERE collection_id=%s AND article_id=%s "
                "RETURNING article_id",
                (collection_id, article_id),
            ).fetchone()
            if row:
                db.execute(
                    "UPDATE article_collections SET updated_at=now() WHERE id=%s", (collection_id,)
                )
        return self.get(user_id, collection_id)

    def import_bookmarks(self, user_id, ids):
        snapshots = {}
        for article_id in dict.fromkeys(ids):
            try:
                snapshots[article_id] = self.snapshot(user_id, article_id)
            except ValueError:
                continue
        if snapshots:
            with self.pool.connection() as db:
                self.lock_reader(db, user_id)
                row = db.execute(
                    "INSERT INTO article_collections (id,user_id,name,import_key) "
                    "VALUES (%s,%s,'À lire','browser-bookmarks-v1') "
                    "ON CONFLICT (user_id,import_key) DO UPDATE SET import_key=excluded.import_key "
                    "RETURNING id",
                    (uuid4().hex, user_id),
                ).fetchone()
                for article_id, payload in snapshots.items():
                    self.insert_saved(db, user_id, article_id, payload)
                    self.insert_member(db, row[0], article_id, payload)
        return {"imported_ids": list(snapshots)}

    @staticmethod
    def lock_reader(db, user_id):
        # Serialize a bookmark removal with collection additions for the same reader.
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1))", (user_id,))

    @staticmethod
    def insert_saved(db, user_id, article_id, payload):
        db.execute(
            "INSERT INTO saved_articles (user_id,article_id,payload) VALUES (%s,%s,%s) "
            "ON CONFLICT DO NOTHING",
            (user_id, article_id, Jsonb(payload)),
        )

    def saved(self, user_id):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            rows = cur.execute(
                "SELECT s.*, a.payload AS current_article FROM saved_articles s "
                "LEFT JOIN articles a ON a.id=s.article_id WHERE s.user_id=%s "
                "ORDER BY s.saved_at DESC, s.article_id",
                (user_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = {**row["payload"], "saved_at": row["saved_at"]}
            if row["current_article"]:
                article = Article.model_validate(row["current_article"])
                item.update(
                    title=article.title,
                    url=article.url,
                    source=article.source,
                    format=article.format,
                    media=article.media,
                    image=article.image.model_dump() if article.image else None,
                    image_checked=bool(article.image_checked_at),
                    reading_time_minutes=article.reading_time_minutes,
                )
            items.append(item)
        return {"article_ids": [item["article_id"] for item in items], "items": items}

    def save(self, user_id, article_id, cover_id=None):
        payload = self.snapshot(user_id, article_id, cover_id)
        with self.pool.connection() as db:
            self.lock_reader(db, user_id)
            self.insert_saved(db, user_id, article_id, payload)
        return self.saved(user_id)

    def unsave(self, user_id, article_id):
        with self.pool.connection() as db:
            self.lock_reader(db, user_id)
            db.execute(
                "WITH removed AS (DELETE FROM collection_articles m USING article_collections c "
                "WHERE m.collection_id=c.id AND c.user_id=%s AND m.article_id=%s "
                "RETURNING m.collection_id) UPDATE article_collections SET updated_at=now() "
                "WHERE id IN (SELECT collection_id FROM removed)",
                (user_id, article_id),
            )
            db.execute(
                "DELETE FROM saved_articles WHERE user_id=%s AND article_id=%s",
                (user_id, article_id),
            )
        return self.saved(user_id)


def repository(request):
    return Collections(request.app.state.store)


def call(action):
    try:
        return action()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("")
def list_collections(request: Request, user_id: str = Query(min_length=1, max_length=100)):
    return repository(request).list(user_id)


@router.post("", status_code=201)
def create_collection(
    data: CollectionInput, request: Request, user_id: str = Query(min_length=1, max_length=100)
):
    return repository(request).create(user_id, data)


@router.post("/import-bookmarks")
def import_bookmarks(
    data: ImportBookmarks, request: Request, user_id: str = Query(min_length=1, max_length=100)
):
    return repository(request).import_bookmarks(user_id, data.article_ids)


@router.get("/{collection_id}")
def get_collection(
    collection_id: str, request: Request, user_id: str = Query(min_length=1, max_length=100)
):
    return call(lambda: repository(request).get(user_id, collection_id))


@router.patch("/{collection_id}")
def edit_collection(
    collection_id: str,
    data: CollectionInput,
    request: Request,
    user_id: str = Query(min_length=1, max_length=100),
):
    return call(lambda: repository(request).edit(user_id, collection_id, data))


@router.delete("/{collection_id}")
def delete_collection(
    collection_id: str, request: Request, user_id: str = Query(min_length=1, max_length=100)
):
    call(lambda: repository(request).delete(user_id, collection_id))
    return {"deleted": True}


@router.put("/{collection_id}/articles/{article_id}")
def add_article(
    collection_id: str,
    article_id: str,
    data: AddArticle,
    request: Request,
    user_id: str = Query(min_length=1, max_length=100),
):
    return call(lambda: repository(request).add(user_id, collection_id, article_id, data.cover_id))


@router.delete("/{collection_id}/articles/{article_id}")
def remove_article(
    collection_id: str,
    article_id: str,
    request: Request,
    user_id: str = Query(min_length=1, max_length=100),
):
    return call(lambda: repository(request).remove(user_id, collection_id, article_id))
