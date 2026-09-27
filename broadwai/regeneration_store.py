from datetime import timedelta
from statistics import median

from psycopg.rows import dict_row


class RegenerationStore:
    def get_regeneration(self, user_id, day):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(
                "SELECT id,status,started_at,finished_at,estimated_seconds,cover_id "
                "FROM edition_regenerations "
                "WHERE user_id=%s AND regeneration_date=%s AND reset_at IS NULL",
                (user_id, day),
            ).fetchone()

    def claim_regeneration(self, user_id, day, request, now, estimated_seconds=120):
        # The unique partial index enforces the allowance across processes and restarts.
        # Feedback and reservation are committed together before any paid work.
        with self.pool.connection() as db:
            row = db.execute(
                """INSERT INTO edition_regenerations
                   (user_id,regeneration_date,previous_cover_id,reason,started_at,status,
                    estimated_seconds)
                   VALUES (%s,%s,%s,%s,%s,'running',%s)
                   ON CONFLICT DO NOTHING RETURNING id""",
                (user_id, day, request.cover_id, request.reason, now, estimated_seconds),
            ).fetchone()
        return row[0] if row else None

    def finish_regeneration(self, attempt_id, cover_id, now):
        with self.pool.connection() as db:
            db.execute(
                "UPDATE edition_regenerations SET status=%s,cover_id=%s,finished_at=%s "
                "WHERE id=%s AND status='running' AND reset_at IS NULL",
                ("completed" if cover_id else "failed", cover_id, now, attempt_id),
            )

    def reset_regeneration(self, user_id, day, now):
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT id,status,started_at FROM edition_regenerations "
                "WHERE user_id=%s AND regeneration_date=%s AND reset_at IS NULL FOR UPDATE",
                (user_id, day),
            ).fetchone()
            if row is None:
                return False
            if row[1] == "running" and row[2] >= now - timedelta(minutes=10):
                raise ValueError(
                    "Une régénération est en cours. Attendez sa fin avant de réinitialiser."
                )
            db.execute(
                "UPDATE edition_regenerations SET reset_at=%s, "
                "status=CASE WHEN status='running' THEN 'failed' ELSE status END "
                "WHERE id=%s",
                (now, row[0]),
            )
        return True

    def estimate_regeneration_seconds(self, user_id):
        with self.pool.connection() as db:
            rows = db.execute(
                "SELECT EXTRACT(EPOCH FROM finished_at-started_at) FROM edition_regenerations "
                "WHERE user_id=%s AND status='completed' AND finished_at > started_at "
                "ORDER BY finished_at DESC LIMIT 20",
                (user_id,),
            ).fetchall()
        return max(30, min(300, round(median(float(row[0]) for row in rows)))) if rows else 120

    def recent_edition_feedback(self, user_id, now):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            rows = cursor.execute(
                "SELECT r.reason,r.started_at,c.payload->'items' AS previous_items "
                "FROM edition_regenerations r "
                "JOIN covers c ON c.id=r.previous_cover_id "
                "WHERE r.user_id=%s AND r.reason <> '' "
                "AND r.started_at > %s AND r.started_at <= %s "
                "ORDER BY r.started_at DESC,r.id DESC LIMIT 7",
                (user_id, now - timedelta(days=7), now),
            ).fetchall()
        return [
            {
                "reason": row["reason"],
                "created_at": row["started_at"],
                "previous_titles": [
                    (item.get("title") or item.get("headline", ""))[:200]
                    for item in (row["previous_items"] or [])[:20]
                ],
            }
            for row in rows
        ]
