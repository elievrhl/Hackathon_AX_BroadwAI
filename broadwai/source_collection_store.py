from datetime import timedelta
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


class SourceCollectionStore:
    def initialize_source_catalog(self, definitions, now, first_run_at):
        """Import once per database, atomically with the durable collection request."""
        with self.pool.connection() as db:
            db.execute("SELECT pg_advisory_xact_lock(78104322)")
            db.execute(
                "INSERT INTO source_collection_schedule (id, first_run_at) VALUES (TRUE,%s) "
                "ON CONFLICT DO NOTHING",
                (first_run_at,),
            )
            imported = db.execute(
                "SELECT catalog_imported_at FROM source_collection_schedule WHERE id=TRUE"
            ).fetchone()[0]
            if imported is not None:
                return None
            with db.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO sources (id,name,kind,url,enabled,limit_per_source) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(kind,url) DO NOTHING",
                    [
                        (
                            uuid4().hex,
                            row["name"],
                            row["kind"],
                            row["url"],
                            row["enabled"],
                            row["limit_per_source"],
                        )
                        for row in definitions
                    ],
                )
                added = cursor.rowcount
            db.execute(
                "UPDATE source_collection_schedule SET catalog_imported_at=%s WHERE id=TRUE",
                (now,),
            )
        return added

    def initialize_source_collection(self, first_run_at):
        with self.pool.connection() as db:
            db.execute(
                "INSERT INTO source_collection_schedule (id, first_run_at) VALUES (TRUE,%s) "
                "ON CONFLICT DO NOTHING",
                (first_run_at,),
            )

    def claim_source_collection(self, slot, now, *, scheduled=True, bootstrap=False):
        token = uuid4().hex
        with self.pool.connection() as db:
            # Serialize claims, including two workers crossing a date boundary.
            db.execute("SELECT pg_advisory_xact_lock(78104322)")
            schedule = db.execute(
                "SELECT first_run_at,catalog_imported_at,bootstrap_completed_at "
                "FROM source_collection_schedule WHERE id=TRUE"
            ).fetchone()
            if not schedule:
                return None
            initial = bootstrap and schedule[1] is not None and schedule[2] is None
            if not (initial or (scheduled and schedule[0] <= slot)):
                return None
            running = db.execute(
                "SELECT EXISTS (SELECT 1 FROM source_collection_runs WHERE status='running' "
                "AND heartbeat_at > %s)",
                (now - timedelta(minutes=5),),
            ).fetchone()[0]
            if running:
                return None
            row = db.execute(
                """INSERT INTO source_collection_runs
                   (slot_at,status,token,started_at,heartbeat_at)
                   VALUES (%s,'running',%s,%s,%s)
                   ON CONFLICT(slot_at) DO UPDATE SET status='running',token=excluded.token,
                   heartbeat_at=excluded.heartbeat_at,finished_at=NULL,report=NULL
                   WHERE source_collection_runs.status != 'completed' OR %s
                   RETURNING token""",
                (slot, token, now, now, initial),
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
            updated = db.execute(
                "UPDATE source_collection_runs SET status=%s,finished_at=%s,report=%s "
                "WHERE slot_at=%s AND token=%s AND status='running'",
                ("interrupted" if interrupted else "completed", now, Jsonb(report), slot, token),
            ).rowcount
            if updated and not interrupted:
                # A pre-existing worker may have claimed before the catalogue import.
                # Only finish bootstrap after every currently active source was attempted.
                db.execute(
                    "UPDATE source_collection_schedule SET bootstrap_completed_at=%s "
                    "WHERE id=TRUE AND catalog_imported_at IS NOT NULL "
                    "AND bootstrap_completed_at IS NULL AND NOT EXISTS ("
                    "SELECT 1 FROM sources WHERE enabled AND "
                    "(last_collected_at IS NULL OR last_collected_at < %s))",
                    (now, slot),
                )

    def source_collection_status(self):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
            schedule = cursor.execute(
                "SELECT first_run_at,catalog_imported_at,bootstrap_completed_at "
                "FROM source_collection_schedule WHERE id=TRUE"
            ).fetchone()
            run = cursor.execute(
                "SELECT slot_at,status,started_at,heartbeat_at,finished_at,report "
                "FROM source_collection_runs ORDER BY slot_at DESC LIMIT 1"
            ).fetchone()
        return {
            **(schedule or {}),
            "first_run_at": schedule["first_run_at"] if schedule else None,
            "last_run": run,
        }
