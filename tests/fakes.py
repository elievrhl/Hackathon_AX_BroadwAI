from datetime import timedelta

from broadwai.llm import ModelError
from broadwai.models import (
    Article,
    Brief,
    Decision,
    EditorialPlan,
    PreferenceAssessments,
    ReaderPreference,
    utcnow,
)
from broadwai.preferences import PreferenceConflict, target_key, validate_preference
from broadwai.reader_chat import check_replay, preference_snapshot, prepare_changes
from tests.daily_fakes import MemoryDailyStore


class MemoryStore(MemoryDailyStore):
    """Test double only: the production repository is PostgreSQL."""

    def __init__(self, articles=()):
        super().__init__()
        self.rows = {a.id: a for a in articles}
        self.briefs = {}
        self.covers = {}
        self.feedback = set()
        self.likes = {}
        self.image_reviews = {}
        self.preferences = {}
        self.feedback_details = {}
        self.reader_messages = {}

    def list_reader_messages(self, user_id):
        return [v for (user, _), v in self.reader_messages.items() if user == user_id][-30:]

    def get_reader_message(self, user_id, id_):
        return self.reader_messages.get((user_id, id_))

    def save_reader_message(self, user_id, request, reply, snapshot, usage):
        previous = self.get_reader_message(user_id, request.id)
        if previous:
            return check_replay(previous, request)
        rows = self.list_preferences(user_id, active_only=True)
        if preference_snapshot(rows) != snapshot:
            raise PreferenceConflict("La fiche a changé")
        changes = prepare_changes(user_id, rows, reply)
        for change in changes:
            value = ReaderPreference.model_validate(change["preference"])
            self.preferences[value.id] = value
        turn = {
            "id": request.id,
            "message": request.message,
            "reply": reply.reply,
            "changes": changes,
            "created_at": utcnow().isoformat(),
            "usage": usage,
        }
        self.reader_messages[user_id, request.id] = turn
        return turn

    def list_preferences(self, user_id, *, active_only=False):
        return [
            p
            for p in self.preferences.values()
            if p.user_id == user_id and (not active_only or p.status == "active")
        ]

    def create_preference(self, user_id, value):
        value = validate_preference(value)
        if value.id in self.preferences:
            old = self.preferences[value.id]
            if old.user_id != user_id:
                raise PreferenceConflict("Identifiant déjà utilisé")
            return old
        previous = [
            p
            for p in self.list_preferences(user_id, active_only=True)
            if target_key(p) == target_key(value)
        ]
        if len(self.list_preferences(user_id, active_only=True)) - len(previous) >= 12:
            raise ValueError("12 préférences actives maximum")
        for p in previous:
            self.preferences[p.id] = p.model_copy(
                update={"status": "replaced", "revision": p.revision + 1}
            )
        new = ReaderPreference(**value.model_dump(), user_id=user_id)
        self.preferences[new.id] = new
        return new

    def update_preference(self, user_id, id_, value=None, *, revision=None):
        if value:
            value = validate_preference(value)
            revision = value.revision
        old = self.preferences.get(id_)
        if not old or old.user_id != user_id:
            raise KeyError("Préférence introuvable")
        if old.revision != revision or old.status != "active":
            raise PreferenceConflict("Préférence modifiée entre-temps")
        changes = value.model_dump(exclude={"revision"}) if value else {"status": "deleted"}
        new = old.model_copy(update={**changes, "revision": old.revision + 1})
        for p in self.list_preferences(user_id, active_only=True):
            if p.id != id_ and target_key(p) == target_key(new):
                self.preferences[p.id] = p.model_copy(
                    update={"status": "replaced", "revision": p.revision + 1}
                )
        self.preferences[id_] = new
        return new

    def put_article(self, article):
        previous = self.rows.get(article.id)
        if previous and previous.extraction_status == "extracted" and not article.text:
            return previous
        self.rows[article.id] = article
        return article

    def get_article(self, article_id):
        return self.rows.get(article_id)

    def set_article_image(self, article_id, image, checked_at):
        if article_id in self.rows:
            self.rows[article_id] = self.rows[article_id].model_copy(
                update={"image": image, "image_checked_at": checked_at}
            )

    def article_has_cover(self, article_id):
        return any(item.article_id == article_id for c in self.covers.values() for item in c.items)

    def get_image_review(self, cache_key):
        return self.image_reviews.get(cache_key)

    def claim_image_review(self, cache_key, article_id, claim_id, metadata):
        previous = self.image_reviews.get(cache_key)
        if previous and (previous["status"] == "completed" or previous["retry_after"] > utcnow()):
            return False
        self.image_reviews[cache_key] = {
            **metadata,
            "article_id": article_id,
            "claim_id": claim_id,
            "status": "pending",
            "retry_after": utcnow() + timedelta(minutes=10),
        }
        return True

    def finish_image_review(self, cache_key, claim_id, payload):
        previous = self.image_reviews[cache_key]
        if previous["claim_id"] == claim_id:
            previous.update(
                payload,
                status="error" if payload.get("error") else "completed",
                retry_after=utcnow() + timedelta(hours=24) if payload.get("error") else None,
            )

    def articles(self, limit=3000):
        return list(self.rows.values())[:limit]

    def get_brief(self, article, version):
        return self.briefs.get((article.id, article.content_hash, version))

    def put_brief(self, article, version, brief):
        self.briefs[article.id, article.content_hash, version] = brief

    def put_cover(self, cover, preferences=()):
        self.covers[cover.id] = cover
        if cover.items:
            for p in preferences:
                current = self.preferences.get(p.id)
                if (
                    current
                    and p.scope == "next"
                    and current.status == "active"
                    and current.revision == p.revision
                ):
                    self.preferences[p.id] = current.model_copy(
                        update={
                            "status": "applied",
                            "applied_cover_id": cover.id,
                            "revision": p.revision + 1,
                        }
                    )

    def get_cover(self, cover_id):
        return self.covers.get(cover_id)

    def list_covers(self, limit=30, offset=0):
        covers = sorted(self.covers.values(), key=lambda c: c.created_at, reverse=True)
        return [
            {
                "id": c.id,
                "title": c.title,
                "created_at": c.created_at.isoformat(),
                "status": c.status,
                "item_count": len(c.items),
                "usage": c.usage,
                "audit_version": str(c.diagnostics.get("version", 0)),
            }
            for c in covers[offset : offset + limit]
        ]

    def add_feedback(self, event):
        cover = self.covers.get(event.cover_id)
        if not cover or cover.user_id != event.user_id:
            raise ValueError("Couverture introuvable pour cet utilisateur")
        if event.article_id not in {item.article_id for item in cover.items}:
            raise ValueError("Article absent de cette couverture")
        preference = (
            self.create_preference(event.user_id, event.preference) if event.preference else None
        )
        self.feedback.add((event.user_id, event.article_id, event.kind))
        self.feedback_details[event.user_id, event.cover_id, event.article_id, event.kind] = {
            "article_id": event.article_id,
            "kind": event.kind,
            "reason": event.reason,
            "comment": event.comment,
            "preference_id": preference.id if preference else None,
        }
        return preference

    def feedback_for_cover(self, user_id, cover_id):
        cover = self.get_cover(cover_id)
        if not cover or cover.user_id != user_id:
            raise KeyError("Couverture introuvable")
        return [
            v
            for (user, cover, _, _), v in self.feedback_details.items()
            if user == user_id and cover == cover_id
        ]

    def liked_ids(self, user_id):
        return [id_ for user, id_ in self.likes if user == user_id]

    def reading_memory(self, user_id):
        from broadwai.reader_memory import reading_memory

        return reading_memory([item for (user, _), item in self.likes.items() if user == user_id])

    def set_like(self, event):
        cover = self.covers.get(event.cover_id)
        if not cover or cover.user_id != event.user_id:
            raise ValueError("Couverture introuvable pour cet utilisateur")
        item = next((i for i in cover.items if i.article_id == event.article_id), None)
        if item is None:
            raise ValueError("Article absent de cette couverture")
        if event.liked:
            self.likes.setdefault((event.user_id, event.article_id), item.model_dump(mode="json"))
        else:
            self.likes.pop((event.user_id, event.article_id), None)

    def consumed_ids(self, user_id):
        return {
            id_ for user, id_, kind in self.feedback if user == user_id and kind != "impression"
        } | set(self.liked_ids(user_id))

    def stats(self):
        return {"articles": len(self.rows), "briefs": len(self.briefs), "covers": len(self.covers)}


class ScriptedModel:
    """Scripted decisions test orchestration, never claimed to be an AI agent."""

    summary_version = "test-v1"

    def __init__(self, decisions=()):
        self.decisions = list(decisions)
        self.states = []
        self.summary_calls = 0

    async def interpret(self, state, budget):
        from broadwai.models import EditorialIntent, ReaderNeed

        budget.take("intent")
        profile = state["profile"]
        return EditorialIntent(
            needs=[
                ReaderNeed(
                    topic=i["topic"],
                    query=i["topic"],
                    priority="primary",
                    level=profile["level"],
                    evidence=i["topic"],
                )
                for i in profile["interests"]
            ]
        )

    async def assess_preferences(self, state, budget):
        budget.take("preferences")
        self.states.append(state)
        return PreferenceAssessments(
            assessments=[
                {
                    "article_id": c["article_id"],
                    "preference_id": p["id"],
                    "match": "yes" if p["target"].casefold() in c["title"].casefold() else "no",
                    "evidence": c["title"],
                }
                for c in state["candidates"]
                for p in state["preferences"]
            ]
        )

    async def summarize(self, article, budget):
        budget.take("summary")
        self.summary_calls += 1
        return Brief(
            summary=article.excerpt or article.text[:300],
            key_points=["Point factuel de test"],
            topics=["Python"],
            content_type="analysis",
            level="intermediate",
            language="fr",
            caveats=[],
        )

    async def decide(self, state, budget):
        budget.take("editor")
        self.states.append(state)
        if not self.decisions:
            raise ModelError("Fin du scénario de test")
        result = self.decisions.pop(0)
        return result(state) if callable(result) else result

    async def plan(self, state, budget):
        budget.take("plan")
        return EditorialPlan(
            sections=["Technique"],
            picks=[
                {
                    "article_id": c["article_id"],
                    "section": "Technique",
                    "score": 80,
                    "reason": "Correspond au profil de test",
                    "matches_profile": True,
                    "evergreen": False,
                }
                for c in state["candidates"][: state["selection_limit"]]
            ],
            gaps=[],
            queries=[],
        )

    async def screen(self, state, budget):
        budget.take("screen")
        return EditorialPlan(
            sections=state["sections"] or ["Technique"],
            picks=[
                {
                    "article_id": c["article_id"],
                    "section": (state["sections"] or ["Technique"])[0],
                    "score": 80,
                    "reason": "Correspond au profil de test",
                    "matches_profile": True,
                    "evergreen": False,
                }
                for c in state["candidates"][: state["selection_limit"]]
            ],
            gaps=[],
            queries=[],
        )


class FakeSearch:
    enabled = True

    def __init__(self, articles=()):
        self.articles = list(articles)
        self.queries = []

    async def search(self, query, budget, limit=5, *, context=None):
        self.queries.append(query)
        return self.articles[:limit]


class FakeCollector:
    def __init__(self, store):
        self.store = store
        self.calls = []

    async def extract(self, article):
        self.calls.append(article.id)
        return self.store.put_article(
            article.model_copy(
                update={
                    "text": (article.excerpt or "Texte de test factuel. ") * 6,
                    "extraction_status": "extracted",
                    "published_at": article.published_at or utcnow(),
                }
            )
        )


def article(index=1, *, title=None, source=None, extracted=True):
    return Article.create(
        url=f"https://{source or f'source{index}.example'}/article/{index}",
        title=title or f"Python et systèmes distribués : étude {index}",
        excerpt="Un article sur Python et les systèmes distribués, avec des résultats "
        "concrets sur les performances et la fiabilité des applications.",
        text=(f"Python systèmes distribués : analyse {index}, {title or 'performance'}. " * 10)
        if extracted
        else "",
        extraction_status="extracted" if extracted else "excerpt",
        language="fr",
        published_at=utcnow(),
    )


def decision(action="finalize", **kwargs):
    return Decision(
        action=action,
        justification="Justification observable du test",
        query=kwargs.get("query"),
        article_id=kwargs.get("article_id"),
        title=kwargs.get("title", "Votre briefing"),
        selections=kwargs.get("selections", []),
        source_url=kwargs.get("source_url"),
    )


def finalize_first(state):
    return decision(
        selections=[
            {
                "article_id": state["candidates"][0]["article_id"],
                "section": "Technique",
                "reason": "Correspond à Python",
            }
        ]
    )
