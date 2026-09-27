from datetime import timedelta
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class SourceCollectionStore:
    def initialize_source_collection(self, first_run_at):
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO source_collection_schedule (id, first_run_at) VALUES (TRUE,%s) "
                "ON CONFLICT DO NOTHING",
                (first_run_at,),
            )

    def claim_source_collection(self, slot, now):
        token = uuid4().hex
        with self.pool.connection() as db:
            # Serialize claims, including two workers crossing a date boundary.
            db.execute("SELECT pg_advisory_xact_lock(78104322)")
            ready = db.execute(
                "SELECT EXISTS (SELECT 1 FROM source_collection_schedule "
                "WHERE first_run_at <= %s) AND NOT EXISTS ("
                "SELECT 1 FROM source_collection_runs WHERE status='running' "
                "AND heartbeat_at > %s)",
                (slot, now - timedelta(minutes=5)),
            ).fetchone()[0]
            if not ready:
                return None
            row = db.execute(
                """INSERT INTO source_collection_runs
                   (slot_at,status,token,started_at,heartbeat_at)
                   VALUES (%s,'running',%s,%s,%s)
                   ON CONFLICT(slot_at) DO UPDATE SET status='running',token=excluded.token,
                   heartbeat_at=excluded.heartbeat_at,finished_at=NULL,report=NULL
                   WHERE source_collection_runs.status != 'completed'
                   RETURNING token""",
                (slot, token, now, now),
            ).fetchone()
        return row[0] if row else None

    def touch_source_collection(self, slot, token, now):
        with self.pool.connection() as db:
            return (
                db.execute(
                    "UPDATE source_collection_runs SET heartbeat_at=%s "
                    "WHERE slot_at=%s AND token=%s AND status='running'",
                    (now, slot, token),
                ).rowcount
                == 1
            )

    def finish_source_collection(self, slot, token, now, report, *, interrupted=False):
        with self.pool.connection() as db:
            db.execute(
                "UPDATE source_collection_runs SET status=%s,finished_at=%s,report=%s "
                "WHERE slot_at=%s AND token=%s AND status='running'",
                ("interrupted" if interrupted else "completed", now, Jsonb(report), slot, token),
            )

    def source_collection_status(self):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            schedule = cursor.execute(
                "SELECT first_run_at FROM source_collection_schedule WHERE id=TRUE"
            ).fetchone()
            run = cursor.execute(
                "SELECT slot_at,status,started_at,heartbeat_at,finished_at,report "
                "FROM source_collection_runs ORDER BY slot_at DESC LIMIT 1"
            ).fetchone()
        return {"first_run_at": schedule["first_run_at"] if schedule else None, "last_run": run}
