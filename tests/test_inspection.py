import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.models import CitedSource, Cover
from tests.fakes import MemoryStore, ScriptedModel, article, finalize_first
from tests.test_pipeline import pipeline, request


async def test_journal_records_scores_summary_cache_and_exact_decisions():
    item = article()
    store = MemoryStore([item])
    model = ScriptedModel([finalize_first, finalize_first])
    first = await pipeline(store, model).run(request())
    second = await pipeline(store, model).run(request())
    events = first.diagnostics["events"]
    kinds = [e["kind"] for e in events]
    assert kinds.index("shortlist") < kinds.index("summary_requested")
    assert kinds.index("summary_completed") < kinds.index("editor_requested")
    assert kinds[-1] == "cover_completed"
    shortlist = next(e for e in events if e["kind"] == "shortlist")
    assert shortlist["shortlisted_ids"] == [item.id]
    score = shortlist["ranked"][0]
    parts = score["score_details"]
    assert score["score"] == pytest.approx(
        sum(parts["interests"].values())
        + parts["query_bonus"]
        + parts["freshness"]
        + sum(parts["needs"].values())
        + 2 * parts["notes"]
    )
    assert first.diagnostics["candidates"][0]["brief"] == first.items[0].brief.model_dump()
    assert "summary_cache_hit" in [e["kind"] for e in second.diagnostics["events"]]
    assert "summary_requested" not in [e["kind"] for e in second.diagnostics["events"]]
    assert "openai_api_key" not in first.diagnostics["settings"]
    assert first.diagnostics["request"]["profile"]["user_id"] == "alice"


async def test_history_and_legacy_cover_remain_readable_without_reconstruction():
    store = MemoryStore([article()])
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(request())
    old = cover.model_dump()
    old.pop("diagnostics")
    old["id"] = "legacy"
    store.put_cover(Cover.model_validate(old))
    with TestClient(create_app(Settings(_env_file=None), store=store)) as client:
        assert client.get("/admin/covers").status_code == 200
        assert client.get("/v1/covers?limit=1").json()[0]["item_count"] == 1
        assert client.get("/v1/covers/legacy").json()["diagnostics"] == {}
        assert client.get("/v1/covers?limit=101").status_code == 422


async def test_cited_sources_survive_cache_and_are_exposed_in_admin_audit():
    from tests.admin_fakes import AdminStore

    source = CitedSource(
        name="Rapport Python",
        url="https://research.example/report",
        relevance="Travail original sur les systèmes distribués.",
        evidence="Python systèmes distribués",
    )

    class ModelWithSources(ScriptedModel):
        async def summarize(self, item, budget):
            brief = await super().summarize(item, budget)
            return brief.model_copy(update={"cited_sources": [source]})

    item = article()
    store = AdminStore()
    store.put_article(item)
    model = ModelWithSources([finalize_first, finalize_first])
    first = await pipeline(store, model).run(request())
    second = await pipeline(store, model).run(request())
    assert model.summary_calls == 1
    for cover in [first, second]:
        event = next(e for e in cover.diagnostics["events"] if e["kind"] == "cited_sources")
        assert event["sources"] == [source.model_dump()]
        assert event["url"] == item.url
        assert cover.items[0].brief.cited_sources == [source]
    with TestClient(create_app(Settings(_env_file=None), store=store)) as client:
        detail = client.get(f"/v1/admin/articles/{item.id}").json()
        assert detail["briefs"][0]["payload"]["cited_sources"] == [source.model_dump()]
        cover = client.get(f"/v1/covers/{second.id}").json()
        event = next(e for e in cover["diagnostics"]["events"] if e["kind"] == "cited_sources")
        assert event["sources"][0]["relevance"] == source.relevance
        assert client.get("/admin/assets/cited-sources.js").status_code == 200
