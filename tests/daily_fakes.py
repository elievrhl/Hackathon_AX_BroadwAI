from datetime import timedelta


class MemoryDailyStore:
    def __init__(self):
        self.daily_profiles = {}
        self.daily_runs = {}

    def list_daily_profiles(self, limit=100, offset=0):
        return [
            {"user_id": user, **profile}
            for user, profile in self.daily_profiles.items()
        ][offset:offset + limit]

    def get_daily_profile(self, user_id):
        return self.daily_profiles.get(user_id, {}).get("request")

    def has_due_daily_edition(self, slot):
        return any(
            profile["first_run_at"] <= slot and (user, slot.date()) not in self.daily_runs
            for user, profile in self.daily_profiles.items()
        )

    def save_daily_profile(self, request, first_run_at, now):
        user = request.profile.user_id
        previous = self.daily_profiles.get(user, {})
        self.daily_profiles[user] = {
            "request": request.model_dump(mode="json"),
            "first_run_at": previous.get("first_run_at", first_run_at),
            "updated_at": now,
        }

    def daily_edition_status(self, user_id):
        runs = [run for (user, day), run in self.daily_runs.items() if user == user_id]
        return {
            "first_run_at": self.daily_profiles.get(user_id, {}).get("first_run_at"),
            "run": max(runs, key=lambda run: run["edition_date"]) if runs else None,
        }

    def claim_daily_edition(self, slot, now):
        for run in self.daily_runs.values():
            if run["status"] == "running" and run["started_at"] < now - timedelta(minutes=10):
                run["status"] = "failed"
        for user, profile in self.daily_profiles.items():
            key = (user, slot.date())
            if profile["first_run_at"] <= slot and key not in self.daily_runs:
                self.daily_runs[key] = {
                    "edition_date": slot.date(),
                    "status": "running",
                    "started_at": now,
                    "cover_id": None,
                }
                return {"user_id": user, "edition_date": slot.date(), "request": profile["request"]}
        return None

    def finish_daily_edition(self, user_id, day, cover_id):
        self.daily_runs[user_id, day].update(
            status="completed" if cover_id else "failed",
            cover_id=cover_id,
        )
