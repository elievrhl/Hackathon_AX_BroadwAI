from psycopg.types.json import Jsonb

from broadwai.models import ReaderPreference, utcnow
from broadwai.preferences import PreferenceConflict, target_key, validate_preference
from broadwai.reader_chat import check_replay, preference_snapshot, prepare_changes


class PreferenceStore:
    def list_reader_messages(self, user_id):
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT payload FROM reader_messages WHERE user_id=%s "
                "ORDER BY created_at DESC, id DESC LIMIT 30",
                (user_id,),
            ).fetchall()
        return [row[0] for row in reversed(rows)]

    def get_reader_message(self, user_id, id_):
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT payload FROM reader_messages WHERE user_id=%s AND id=%s",
                (user_id, id_),
            ).fetchone()
        return row[0] if row else None

    def save_reader_message(self, user_id, request, reply, snapshot, usage):
        with self.pool.connection() as db:
            self._preference_lock(db, user_id)
            previous = db.execute(
                "SELECT payload FROM reader_messages WHERE user_id=%s AND id=%s",
                (user_id, request.id),
            ).fetchone()
            if previous:
                return check_replay(previous[0], request)
            rows = [
                ReaderPreference.model_validate(row[0])
                for row in db.execute(
                    "SELECT payload FROM reader_preferences WHERE user_id=%s "
                    "AND payload->>'status'='active'",
                    (user_id,),
                ).fetchall()
            ]
            if preference_snapshot(rows) != snapshot:
                raise PreferenceConflict(
                    "Votre fiche a changé pendant la lecture. Renvoyez votre message."
                )
            changes = prepare_changes(user_id, rows, reply)
            # Release all old target keys first, including when a plan moves a target.
            ids = [c.preference_id for c in reply.changes if c.preference_id]
            for old in rows:
                if old.id in ids:
                    self._write_preference(db, old.model_copy(update={"status": "replaced"}))
            for change in changes:
                self._write_preference(db, ReaderPreference.model_validate(change["preference"]))
            turn = {
                "id": request.id,
                "message": request.message,
                "reply": reply.reply,
                "changes": changes,
                "created_at": utcnow().isoformat(),
                "usage": usage,
            }
            db.execute(
                "INSERT INTO reader_messages (user_id,id,payload) VALUES (%s,%s,%s)",
                (user_id, request.id, Jsonb(turn)),
            )
            return turn

    def list_preferences(self, user_id, *, active_only=False):
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT payload FROM reader_preferences WHERE user_id=%s "
                "ORDER BY payload->>'updated_at' DESC, id",
                (user_id,),
            ).fetchall()
        values = [ReaderPreference.model_validate(row[0]) for row in rows]
        return [v for v in values if not active_only or v.status == "active"]

    def _preference_lock(self, db, user_id):
        db.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 67281))", (user_id,))

    def _write_preference(self, db, preference):
        row = db.execute(
            "INSERT INTO reader_preferences (id,user_id,target_key,payload) VALUES (%s,%s,%s,%s) "
            "ON CONFLICT(id) DO UPDATE SET target_key=excluded.target_key,payload=excluded.payload "
            "WHERE reader_preferences.user_id=excluded.user_id RETURNING id",
            (
                preference.id,
                preference.user_id,
                target_key(preference),
                Jsonb(preference.model_dump(mode="json")),
            ),
        ).fetchone()
        if not row:
            raise PreferenceConflict("Identifiant de préférence déjà utilisé")

    def _replace_target(self, db, preference):
        rows = db.execute(
            "SELECT payload FROM reader_preferences WHERE user_id=%s AND target_key=%s "
            "AND id<>%s AND payload->>'status'='active'",
            (preference.user_id, target_key(preference), preference.id),
        ).fetchall()
        for row in rows:
            old = ReaderPreference.model_validate(row[0])
            self._write_preference(
                db,
                old.model_copy(
                    update={
                        "status": "replaced",
                        "revision": old.revision + 1,
                        "updated_at": utcnow(),
                    }
                ),
            )

    def _create_preference(self, db, user_id, value, *, cover_id=None, article_id=None):
        value = validate_preference(value)
        self._preference_lock(db, user_id)
        row = db.execute(
            "SELECT payload FROM reader_preferences WHERE id=%s", (value.id,)
        ).fetchone()
        if row:
            previous = ReaderPreference.model_validate(row[0])
            if previous.user_id != user_id:
                raise PreferenceConflict("Identifiant de préférence déjà utilisé")
            # Idempotent replay, including a deleted/applied rule: never resurrect it.
            return previous
        preference = ReaderPreference(
            **value.model_dump(),
            user_id=user_id,
            origin_cover_id=cover_id,
            origin_article_id=article_id,
        )
        self._replace_target(db, preference)
        count = db.execute(
            "SELECT count(*) FROM reader_preferences WHERE user_id=%s "
            "AND payload->>'status'='active'",
            (user_id,),
        ).fetchone()[0]
        if count >= 12:
            raise ValueError(
                "12 préférences actives maximum : modifiez ou supprimez une préférence"
            )
        self._write_preference(db, preference)
        return preference

    def create_preference(self, user_id, value):
        with self.pool.connection() as db:
            return self._create_preference(db, user_id, value)

    def update_preference(self, user_id, id_, value=None, *, revision=None):
        if value:
            value = validate_preference(value)
            revision = value.revision
        with self.pool.connection() as db:
            self._preference_lock(db, user_id)
            row = db.execute(
                "SELECT payload FROM reader_preferences WHERE id=%s AND user_id=%s FOR UPDATE",
                (id_, user_id),
            ).fetchone()
            if not row:
                raise KeyError("Préférence introuvable")
            old = ReaderPreference.model_validate(row[0])
            if old.revision != revision or old.status != "active":
                raise PreferenceConflict("Préférence modifiée entre-temps. Actualisez la liste.")
            changes = value.model_dump(exclude={"revision"}) if value else {"status": "deleted"}
            updated = old.model_copy(
                update={
                    **changes,
                    "revision": old.revision + 1,
                    "updated_at": utcnow(),
                }
            )
            if value:
                self._replace_target(db, updated)
            self._write_preference(db, updated)
            return updated

    def _consume_preferences(self, db, cover, preferences):
        if not cover.items:
            return
        self._preference_lock(db, cover.user_id)
        for preference in preferences:
            if preference.scope != "next":
                continue
            row = db.execute(
                "SELECT payload FROM reader_preferences WHERE id=%s AND user_id=%s FOR UPDATE",
                (preference.id, cover.user_id),
            ).fetchone()
            if not row:
                continue
            current = ReaderPreference.model_validate(row[0])
            # A correction submitted during generation belongs to the next generation.
            if current.status == "active" and current.revision == preference.revision:
                self._write_preference(
                    db,
                    current.model_copy(
                        update={
                            "status": "applied",
                            "applied_cover_id": cover.id,
                            "revision": current.revision + 1,
                            "updated_at": utcnow(),
                        }
                    ),
                )
