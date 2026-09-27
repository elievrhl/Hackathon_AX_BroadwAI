from datetime import timedelta
from statistics import median
from threading import Lock


class MemoryRegenerationStore:
    def __init__(self):
        self.regenerations = {}
        self.regeneration_lock = Lock()

    def get_regeneration(self, user_id, day):
        return next(
            (
                row
                for row in self.regenerations.values()
                if row["user_id"] == user_id
                and row["regeneration_date"] == day
                and row["reset_at"] is None
            ),
            None,
        )

    def claim_regeneration(self, user_id, day, request, now, estimated_seconds=120):
        with self.regeneration_lock:
            if self.get_regeneration(user_id, day):
                return None
            attempt_id = len(self.regenerations) + 1
            self.regenerations[attempt_id] = {
                "id": attempt_id,
                "user_id": user_id,
                "regeneration_date": day,
                "reset_at": None,
                "finished_at": None,
                "estimated_seconds": estimated_seconds,
                "status": "running",
                "started_at": now,
                "cover_id": None,
                "previous_cover_id": request.cover_id,
                "reason": request.reason,
            }
            return attempt_id

    def finish_regeneration(self, attempt_id, cover_id, now):
        row = self.regenerations[attempt_id]
        if row["reset_at"] is not None or row["status"] != "running":
            return
        row.update(
            status="completed" if cover_id else "failed",
            cover_id=cover_id,
            finished_at=now,
        )

    def reset_regeneration(self, user_id, day, now):
        with self.regeneration_lock:
            row = self.get_regeneration(user_id, day)
            if row is None:
                return False
            if row["status"] == "running" and row["started_at"] >= now - timedelta(minutes=10):
                raise ValueError(
                    "Une régénération est en cours. Attendez sa fin avant de réinitialiser."
                )
            row["reset_at"] = now
            if row["status"] == "running":
                row["status"] = "failed"
            return True

    def estimate_regeneration_seconds(self, user_id):
        rows = sorted(
            (
                row
                for row in self.regenerations.values()
                if row["user_id"] == user_id
                and row["status"] == "completed"
                and row["finished_at"]
                and row["finished_at"] > row["started_at"]
            ),
            key=lambda row: row["finished_at"],
            reverse=True,
        )[:20]
        return (
            max(
                30,
                min(
                    300,
                    round(
                        median((r["finished_at"] - r["started_at"]).total_seconds() for r in rows)
                    ),
                ),
            )
            if rows
            else 120
        )

    def recent_edition_feedback(self, user_id, now):
        rows = sorted(
            [
                row
                for row in self.regenerations.values()
                if row["user_id"] == user_id
                and row["reason"]
                and now - timedelta(days=7) < row["started_at"] <= now
            ],
            key=lambda row: (row["started_at"], row["id"]),
            reverse=True,
        )[:7]
        return [
            {
                "reason": row["reason"],
                "created_at": row["started_at"],
                "previous_titles": [
                    item.title[:200] for item in self.covers[row["previous_cover_id"]].items[:20]
                ],
            }
            for row in rows
        ]
