from importlib.resources import files
from uuid import uuid4

from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from broadwai.models import Article, Brief, Cover, Feedback


class Store:
    """PostgreSQL repository with a bounded connection pool."""

    def __init__(self, database_url: str):
        self.pool = ConnectionPool(
            database_url,
            min_size=1,
            max_size=5,
            open=False,
            kwargs={"connect_timeout": 5},
            timeout=10,
        )

    def open(self) -> None:
        self.pool.open(wait=True, timeout=10)
        schema = files("broadwai").joinpath("schema.sql").read_text(encoding="utf-8")
        with self.pool.connection() as db:
            db.execute("SELECT pg_advisory_xact_lock(78104321)")
            db.execute(schema)

    def close(self) -> None:
        self.pool.close()

    def put_article(self, article: Article) -> Article:
        with self.pool.connection() as db:
            row = db.execute(
                """INSERT INTO articles (id, url, collected_at, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET payload = CASE
                    WHEN articles.payload->>'extraction_status' = 'extracted'
                     AND excluded.payload->>'extraction_status' = 'excerpt'
                    THEN articles.payload
                    ELSE jsonb_set(excluded.payload, '{collected_at}',
                                   articles.payload->'collected_at') END
                RETURNING payload""",
                (
                    article.id,
                    article.url,
                    article.collected_at,
                    Jsonb(article.model_dump(mode="json")),
                ),
            ).fetchone()
        return Article.model_validate(row[0])

    def get_article(self, article_id: str) -> Article | None:
        with self.pool.connection() as db:
            row = db.execute("SELECT payload FROM articles WHERE id=%s", (article_id,)).fetchone()
        return Article.model_validate(row[0]) if row else None

    def set_article_image(self, article_id, image, checked_at):
        # Patch only artwork; concurrent extraction must not lose text or new metadata.
        with self.pool.connection() as db:
            db.execute(
                "UPDATE articles SET payload = payload || %s WHERE id = %s",
                (
                    Jsonb(
                        {
                            "image": image.model_dump() if image else None,
                            "image_checked_at": checked_at.isoformat(),
                        }
                    ),
                    article_id,
                ),
            )

    def articles(self, limit: int = 3000) -> list[Article]:
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT payload FROM articles ORDER BY collected_at DESC, id LIMIT %s", (limit,)
            ).fetchall()
        return [Article.model_validate(row[0]) for row in rows]

    def article_has_cover(self, article_id):
        with self.pool.connection() as db:
            return db.execute(
                "SELECT EXISTS (SELECT 1 FROM covers WHERE payload @> %s)",
                (Jsonb({"items": [{"article_id": article_id}]}),),
            ).fetchone()[0]

    def get_image_review(self, cache_key):
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT status, payload FROM image_reviews WHERE cache_key=%s", (cache_key,)
            ).fetchone()
        return {"status": row[0], **row[1]} if row else None

    def claim_image_review(self, cache_key, article_id, claim_id, metadata):
        # One paid attempt across workers. Interrupted calls wait 10 min; errors wait 24 h.
        with self.pool.connection() as db:
            row = db.execute(
                """INSERT INTO image_reviews
                   (cache_key, article_id, claim_id, status, payload, retry_after)
                   VALUES (%s, %s, %s, 'pending', %s, now() + interval '10 minutes')
                   ON CONFLICT(cache_key) DO UPDATE SET
                     claim_id=excluded.claim_id, status='pending',
                     payload=excluded.payload || jsonb_build_object('previous_attempts',
                       COALESCE(image_reviews.payload->'previous_attempts', '[]'::jsonb) ||
                       jsonb_build_array(image_reviews.payload - 'previous_attempts')),
                     retry_after=excluded.retry_after, updated_at=now()
                   WHERE image_reviews.status IN ('pending', 'error')
                     AND image_reviews.retry_after <= now()
                   RETURNING cache_key""",
                (cache_key, article_id, claim_id, Jsonb(metadata)),
            ).fetchone()
        return row is not None

    def finish_image_review(self, cache_key, claim_id, payload):
        status = "error" if payload.get("error") else "completed"
        with self.pool.connection() as db:
            db.execute(
                """UPDATE image_reviews SET status=%s, payload=payload || %s,
                   retry_after=CASE WHEN %s='error' THEN now() + interval '24 hours' ELSE NULL END,
                   updated_at=now() WHERE cache_key=%s AND claim_id=%s""",
                (status, Jsonb(payload), status, cache_key, claim_id),
            )

    def get_brief(self, article: Article, version: str) -> Brief | None:
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT payload FROM briefs WHERE article_id=%s AND content_hash=%s AND version=%s",
                (article.id, article.content_hash, version),
            ).fetchone()
        return Brief.model_validate(row[0]) if row else None

    def put_brief(self, article: Article, version: str, brief: Brief) -> None:
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO briefs VALUES (%s, %s, %s, %s) "
                "ON CONFLICT(article_id, content_hash, version) "
                "DO UPDATE SET payload=excluded.payload",
                (article.id, article.content_hash, version, Jsonb(brief.model_dump(mode="json"))),
            )

    def put_cover(self, cover: Cover) -> None:
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO covers VALUES (%s, %s, %s)",
                (cover.id, cover.user_id, Jsonb(cover.model_dump(mode="json"))),
            )

    def get_cover(self, cover_id: str) -> Cover | None:
        with self.pool.connection() as db:
            row = db.execute("SELECT payload FROM covers WHERE id=%s", (cover_id,)).fetchone()
        return Cover.model_validate(row[0]) if row else None

    def list_covers(self, limit=30, offset=0, user_id=None):
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT payload->>'id', payload->>'title', payload->>'created_at', "
                "payload->>'status', jsonb_array_length(payload->'items'), "
                "payload->'usage', COALESCE(payload->'diagnostics'->>'version','0') "
                "FROM covers "
                + ("WHERE user_id=%s " if user_id is not None else "")
                + "ORDER BY payload->>'created_at' DESC, id LIMIT %s OFFSET %s",
                (user_id, limit, offset) if user_id is not None else (limit, offset),
            ).fetchall()
        keys = ("id", "title", "created_at", "status", "item_count", "usage", "audit_version")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def save_edition(self, user_id: str, cover_id: str) -> None:
        from broadwai.library import artwork

        cover = self.get_cover(cover_id)
        if cover is None or cover.user_id != user_id:
            raise ValueError("Revue introuvable pour ce compte")
        # Image discovery often happens after generation. Use the latest catalog
        # metadata so older editions also get their available photographs.
        items = []
        for item in cover.items:
            article = self.get_article(item.article_id)
            if article is not None:
                item = item.model_copy(
                    update={
                        "image": article.image
                        if article.image_checked_at
                        else article.image or item.image,
                        "image_checked": bool(article.image_checked_at) or item.image_checked,
                    }
                )
            items.append(item)
        cover = cover.model_copy(update={"items": items})
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO library_editions (user_id, cover_id, artwork) "
                "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (user_id, cover_id, Jsonb(artwork(cover))),
            )

    def library(self, user_id: str) -> list[dict]:
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT c.id, c.payload->>'title', c.payload->>'created_at', "
                "jsonb_array_length(c.payload->'items'), l.saved_at, l.artwork "
                "FROM library_editions l JOIN covers c ON c.id=l.cover_id "
                "WHERE l.user_id=%s AND c.user_id=l.user_id "
                "ORDER BY l.saved_at DESC, c.id",
                (user_id,),
            ).fetchall()
        keys = ("id", "title", "created_at", "item_count", "saved_at", "artwork")
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def remove_edition(self, user_id: str, cover_id: str) -> None:
        with self.pool.connection() as db:
            db.execute(
                "DELETE FROM library_editions WHERE user_id=%s AND cover_id=%s",
                (user_id, cover_id),
            )

    def add_feedback(self, feedback: Feedback) -> None:
        cover = self.get_cover(feedback.cover_id)
        if not cover or cover.user_id != feedback.user_id:
            raise ValueError("Couverture introuvable pour cet utilisateur")
        if feedback.article_id not in {item.article_id for item in cover.items}:
            raise ValueError("Article absent de cette couverture")
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO feedback (user_id, cover_id, article_id, kind) "
                "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                (feedback.user_id, feedback.cover_id, feedback.article_id, feedback.kind),
            )

    def set_like(self, event) -> None:
        cover = self.get_cover(event.cover_id)
        if cover is None or cover.user_id != event.user_id:
            raise ValueError("Couverture introuvable pour cet utilisateur")
        item = next((i for i in cover.items if i.article_id == event.article_id), None)
        if item is None:
            raise ValueError("Article absent de cette couverture")
        with self.pool.connection() as db:
            if event.liked:
                db.execute(
                    "INSERT INTO article_likes (user_id, article_id, cover_id, payload) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (user_id, article_id) DO NOTHING",
                    (
                        event.user_id,
                        event.article_id,
                        event.cover_id,
                        Jsonb(item.model_dump(mode="json")),
                    ),
                )
            else:
                db.execute(
                    "DELETE FROM article_likes WHERE user_id=%s AND article_id=%s",
                    (event.user_id, event.article_id),
                )

    def liked_ids(self, user_id: str) -> list[str]:
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT article_id FROM article_likes WHERE user_id=%s", (user_id,)
            ).fetchall()
        return [row[0] for row in rows]

    def reading_memory(self, user_id: str) -> dict:
        from broadwai.reader_memory import reading_memory

        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT payload FROM article_likes WHERE user_id=%s "
                "ORDER BY liked_at DESC, article_id LIMIT 100",
                (user_id,),
            ).fetchall()
        return reading_memory([row[0] for row in rows])

    def consumed_ids(self, user_id: str) -> set[str]:
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT DISTINCT article_id FROM feedback WHERE user_id=%s "
                "AND kind IN ('open', 'useful', 'already_known', 'not_interested')",
                (user_id,),
            ).fetchall()
        return {row[0] for row in rows} | set(self.liked_ids(user_id))

    def stats(self) -> dict:
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT (SELECT COUNT(*) FROM articles), "
                "(SELECT COUNT(*) FROM briefs), (SELECT COUNT(*) FROM covers)"
            ).fetchone()
        return dict(zip(("articles", "briefs", "covers"), row, strict=True))

    def list_sources(self) -> list[dict]:
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT s.*, (SELECT COUNT(*) FROM source_articles sa WHERE sa.source_id=s.id) "
                "AS article_count FROM sources s ORDER BY lower(s.name), s.id"
            ).fetchall()

    def save_source(self, data: dict, source_id: str | None = None) -> dict | None:
        values = (
            data["name"],
            data["kind"],
            data["url"],
            data["enabled"],
            data["limit_per_source"],
        )
        try:
            with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
                if source_id:
                    row = cur.execute(
                        "UPDATE sources SET name=%s, kind=%s, url=%s, enabled=%s, "
                        "limit_per_source=%s WHERE id=%s RETURNING *",
                        (*values, source_id),
                    ).fetchone()
                else:
                    row = cur.execute(
                        "INSERT INTO sources (name, kind, url, enabled, limit_per_source, id) "
                        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
                        (*values, uuid4().hex),
                    ).fetchone()
                return row
        except UniqueViolation as exc:
            raise ValueError("Cette source est déjà enregistrée") from exc

    def delete_source(self, source_id: str) -> bool:
        with self.pool.connection() as db:
            return db.execute("DELETE FROM sources WHERE id=%s", (source_id,)).rowcount > 0

    def propose_source(self, url, name, justification, discovered_from, kind="rss"):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            existing = cur.execute(
                "SELECT id FROM sources WHERE kind=%s AND url=%s", (kind, url)
            ).fetchone()
            if existing:
                return {"status": "existing", "source_id": existing["id"], "url": url, "kind": kind}
            return cur.execute(
                "INSERT INTO source_proposals (id,url,name,justification,discovered_from,kind) "
                "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(url) DO UPDATE "
                "SET url=excluded.url RETURNING *",
                (uuid4().hex, url, name, justification, discovered_from, kind),
            ).fetchone()

    def list_proposals(self):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT * FROM source_proposals ORDER BY created_at DESC LIMIT 200"
            ).fetchall()

    def review_proposal(self, proposal_id, approve):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            proposal = cur.execute(
                "SELECT * FROM source_proposals WHERE id=%s FOR UPDATE", (proposal_id,)
            ).fetchone()
            if proposal is None or proposal["status"] != "proposed":
                return proposal
            source_id = None
            if approve:
                source = cur.execute(
                    "INSERT INTO sources (id,name,kind,url,enabled,limit_per_source) "
                    "VALUES (%s,%s,%s,%s,TRUE,20) ON CONFLICT(kind,url) DO UPDATE "
                    "SET url=excluded.url RETURNING id",
                    (uuid4().hex, proposal["name"], proposal["kind"], proposal["url"]),
                ).fetchone()
                source_id = source["id"]
            return cur.execute(
                "UPDATE source_proposals SET status=%s,source_id=%s WHERE id=%s RETURNING *",
                ("approved" if approve else "rejected", source_id, proposal_id),
            ).fetchone()

    def record_collection(self, source_id: str, report: dict) -> None:
        with self.pool.connection() as db:
            db.execute(
                "UPDATE sources SET last_collected_at=now(), last_report=%s WHERE id=%s",
                (Jsonb(report), source_id),
            )
            with db.cursor() as cur:
                cur.executemany(
                    "INSERT INTO source_articles VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    [(source_id, article_id) for article_id in report["article_ids"]],
                )

    def browse_articles(self, q="", source_id=None, status=None, offset=0, limit=25) -> dict:
        clauses, params = [], []
        if q:
            pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append("(a.payload->>'title' ILIKE %s OR a.payload->>'source' ILIKE %s)")
            params.extend([pattern, pattern])
        if source_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM source_articles sa "
                "WHERE sa.article_id=a.id AND sa.source_id=%s)"
            )
            params.append(source_id)
        if status:
            clauses.append("a.payload->>'extraction_status'=%s")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.pool.connection() as db:
            total = db.execute("SELECT COUNT(*) FROM articles a" + where, params).fetchone()[0]
            rows = db.execute(
                "SELECT a.payload - 'text' - 'excerpt', "
                "(SELECT COUNT(*) FROM briefs b WHERE b.article_id=a.id) "
                "FROM articles a"
                + where
                + " ORDER BY a.collected_at DESC, a.id LIMIT %s OFFSET %s",
                (*params, limit, offset),
            ).fetchall()
        return {
            "items": [{**row[0], "brief_count": row[1]} for row in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def article_detail(self, article_id: str) -> dict | None:
        article = self.get_article(article_id)
        if article is None:
            return None
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            briefs = cur.execute(
                "SELECT content_hash, version, payload FROM briefs WHERE article_id=%s "
                "ORDER BY version, content_hash",
                (article_id,),
            ).fetchall()
            sources = cur.execute(
                "SELECT s.id, s.name FROM sources s JOIN source_articles sa ON sa.source_id=s.id "
                "WHERE sa.article_id=%s ORDER BY s.name",
                (article_id,),
            ).fetchall()
        return {
            "article": article.model_dump(mode="json"),
            "sources": sources,
            "briefs": [
                {**b, "current_content": b["content_hash"] == article.content_hash} for b in briefs
            ],
        }
