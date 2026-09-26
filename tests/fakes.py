from broadwai.llm import ModelError
from broadwai.models import Article, Brief, Decision, EditorialPlan, utcnow


class MemoryStore:
    """Test double only: the production repository is PostgreSQL."""

    def __init__(self, articles=()):
        self.rows = {a.id: a for a in articles}
        self.briefs = {}
        self.covers = {}
        self.feedback = set()

    def put_article(self, article):
        previous = self.rows.get(article.id)
        if previous and previous.extraction_status == "extracted" and not article.text:
            return previous
        self.rows[article.id] = article
        return article

    def get_article(self, article_id):
        return self.rows.get(article_id)

    def articles(self, limit=3000):
        return list(self.rows.values())[:limit]

    def get_brief(self, article, version):
        return self.briefs.get((article.id, article.content_hash, version))

    def put_brief(self, article, version, brief):
        self.briefs[article.id, article.content_hash, version] = brief

    def put_cover(self, cover):
        self.covers[cover.id] = cover

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
        self.feedback.add((event.user_id, event.article_id, event.kind))

    def consumed_ids(self, user_id):
        return {
            id_ for user, id_, kind in self.feedback if user == user_id and kind != "impression"
        }

    def stats(self):
        return {"articles": len(self.rows), "briefs": len(self.briefs), "covers": len(self.covers)}


class ScriptedModel:
    """Scripted decisions test orchestration, never claimed to be an AI agent."""

    summary_version = "test-v1"

    def __init__(self, decisions=()):
        self.decisions = list(decisions)
        self.states = []
        self.summary_calls = 0

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
