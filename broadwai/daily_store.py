from datetime import timedelta

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class DailyEditionStore:
    def list_daily_profiles(self, limit=100, offset=0):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            return cursor.execute(
                "SELECT user_id,request,first_run_at,updated_at FROM daily_edition_profiles "
                "ORDER BY updated_at DESC,user_id LIMIT %s OFFSET %s",
                (limit, offset),
            ).fetchall()

    def get_daily_profile(self, user_id):
        with self.pool.connection() as db:
            row = db.execute(
                "SELECT request FROM daily_edition_profiles WHERE user_id=%s",
                (user_id,),
            ).fetchone()
        return row[0] if row else None

    def has_due_daily_edition(self, slot):
        with self.pool.connection() as db:
            return db.execute(
                "SELECT EXISTS (SELECT 1 FROM daily_edition_profiles p "
                "WHERE p.first_run_at <= %s AND NOT EXISTS ("
                "SELECT 1 FROM daily_edition_runs r WHERE r.user_id=p.user_id "
                "AND r.edition_date=%s))",
                (slot, slot.date()),
            ).fetchone()[0]

    def save_daily_profile(self, request, first_run_at, now):
        with self.pool.connection() as db:
            db.execute(
                """INSERT INTO daily_edition_profiles (user_id, request, first_run_at, updated_at)
                   VALUES (%s, %s, %s, %s) ON CONFLICT(user_id) DO UPDATE
                   SET request=excluded.request, updated_at=excluded.updated_at""",
                (
                    request.profile.user_id,
                    Jsonb(request.model_dump(mode="json")),
                    first_run_at,
                    now,
                ),
            )

    def daily_edition_status(self, user_id):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            profile = cursor.execute(
                "SELECT first_run_at FROM daily_edition_profiles WHERE user_id=%s", (user_id,)
            ).fetchone()
            run = cursor.execute(
                "SELECT edition_date,status,started_at,cover_id FROM daily_edition_runs "
                "WHERE user_id=%s ORDER BY edition_date DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return {"first_run_at": profile["first_run_at"] if profile else None, "run": run}

    def claim_daily_edition(self, slot, now):
        with self.pool.connection() as db:
            # Never replay a paid attempt after a crash or ambiguous provider error.
            db.execute(
                "UPDATE daily_edition_runs SET status='failed' "
                "WHERE status='running' AND started_at < %s",
                (now - timedelta(minutes=10),),
            )
            row = db.execute(
                """INSERT INTO daily_edition_runs (user_id,edition_date,started_at,status)
                   SELECT p.user_id,%s,%s,'running' FROM daily_edition_profiles p
                   WHERE p.first_run_at <= %s AND NOT EXISTS (
                     SELECT 1 FROM daily_edition_runs r WHERE r.user_id=p.user_id
                     AND r.edition_date=%s)
                   ORDER BY p.first_run_at,p.user_id LIMIT 1
                   ON CONFLICT DO NOTHING RETURNING user_id""",
                (slot.date(), now, slot, slot.date()),
            ).fetchone()
            if not row:
                return None
            request = db.execute(
                "SELECT request FROM daily_edition_profiles WHERE user_id=%s", (row[0],)
            ).fetchone()[0]
        return {"user_id": row[0], "edition_date": slot.date(), "request": request}

    def finish_daily_edition(self, user_id, day, cover_id):
        with self.pool.connection() as db:
            db.execute(
                "UPDATE daily_edition_runs SET status=%s,cover_id=%s "
                "WHERE user_id=%s AND edition_date=%s AND status='running'",
                ("completed" if cover_id else "failed", cover_id, user_id, day),
            )
