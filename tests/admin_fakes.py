from uuid import uuid4

from broadwai.models import utcnow
from tests.fakes import MemoryStore, article


class AdminStore(MemoryStore):
    def __init__(self, articles=()):
        super().__init__(articles)
        self.sources = {}
        self.memberships = set()

    def list_proposals(self):
        return []

    def list_sources(self):
        return [
            {**source, "article_count": sum(s == source["id"] for s, _ in self.memberships)}
            for source in sorted(self.sources.values(), key=lambda s: s["name"].lower())
        ]

    def save_source(self, data, source_id=None):
        if source_id and source_id not in self.sources:
            return None
        if any(
            s["id"] != source_id and (s["kind"], s["url"]) == (data["kind"], data["url"])
            for s in self.sources.values()
        ):
            raise ValueError("Cette source est déjà enregistrée")
        source_id = source_id or uuid4().hex
        source = {
            "id": source_id,
            "last_collected_at": None,
            "last_report": None,
            **self.sources.get(source_id, {}),
            **data,
        }
        self.sources[source_id] = source
        return source

    def delete_source(self, source_id):
        self.memberships = {(s, a) for s, a in self.memberships if s != source_id}
        return self.sources.pop(source_id, None) is not None

    def record_collection(self, source_id, report):
        self.sources[source_id].update(last_collected_at=utcnow(), last_report=report)
        self.memberships.update((source_id, id_) for id_ in report["article_ids"])

    def browse_articles(self, q="", source_id=None, status=None, offset=0, limit=25):
        articles = [
            a
            for a in self.rows.values()
            if (not source_id or (source_id, a.id) in self.memberships)
            and (not status or a.extraction_status == status)
            and (not q or q.lower() in (a.title + a.source).lower())
        ]
        articles.sort(key=lambda a: (a.collected_at, a.id), reverse=True)
        return {
            "total": len(articles),
            "offset": offset,
            "limit": limit,
            "items": [
                {
                    **a.model_dump(mode="json", exclude={"text", "excerpt"}),
                    "brief_count": sum(id_ == a.id for id_, _, _ in self.briefs),
                }
                for a in articles[offset : offset + limit]
            ],
        }

    def article_detail(self, article_id):
        article = self.get_article(article_id)
        if not article:
            return None
        return {
            "article": article.model_dump(mode="json"),
            "sources": [
                {"id": s["id"], "name": s["name"]}
                for s in self.sources.values()
                if (s["id"], article_id) in self.memberships
            ],
            "briefs": [
                {
                    "version": version,
                    "content_hash": hash_,
                    "current_content": hash_ == article.content_hash,
                    "payload": brief.model_dump(mode="json"),
                }
                for (id_, hash_, version), brief in self.briefs.items()
                if id_ == article_id
            ],
        }


class AdminCollector:
    def __init__(self, store):
        self.store = store
        self.calls = []

    async def ingest(self, request):
        self.calls.append(request)
        if any("broken" in url for url in request.feed_urls):
            return {"article_ids": [], "collected": 0, "errors": [{"error": "Flux inaccessible"}]}
        item = article(20, title="Python : organiser les tâches asynchrones", extracted=False)
        self.store.put_article(item)
        return {"article_ids": [item.id], "collected": 1, "errors": []}
