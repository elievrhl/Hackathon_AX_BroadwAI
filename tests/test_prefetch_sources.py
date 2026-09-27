import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from broadwai.discovery import source_article_candidates
from broadwai.llm import BudgetExceeded, OpenAILanguageModel, RunBudget
from broadwai.network import Download, RetrievalError
from broadwai.web_search import OpenAIWebSearch, SourceReference
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    decision,
    finalize_first,
)
from tests.test_pipeline import pipeline, request
from tests.test_retrieval import FEED
from tests.test_website import LISTING, ROOT, fetcher_for, story


class InspectingModel(ScriptedModel):
    async def plan(self, state, budget):
        self.previews = state["candidates"]
        assert self.summary_calls == 0
        return await super().plan(state, budget)


async def test_fetch_precedes_editorial_plan_and_is_reused_by_preparation():
    good = article(1, extracted=False)
    blocked = article(2, extracted=False).model_copy(update={"excerpt": ""})
    store = MemoryStore([good, blocked])
    collector = FakeCollector(store)
    original = collector.extract

    async def extract(item):
        if item.id == blocked.id:
            collector.calls.append(item.id)
            raise RetrievalError("Article bloqué")
        return await original(item)

    collector.extract = extract
    model = InspectingModel([finalize_first])
    cover = await pipeline(store, model, collector=collector).run(request())
    assert [c["article_id"] for c in model.previews] == [good.id]
    assert model.previews[0]["access"]["status"] == "full_text"
    assert collector.calls.count(good.id) == 1
    assert collector.calls.count(blocked.id) == 1
    kinds = [event["kind"] for event in cover.diagnostics["events"]]
    assert kinds.index("extract_completed") < kinds.index("editorial_preview")
    assert kinds.index("prefetch_completed") < kinds.index("summary_requested")
    assert model.summary_calls == 1
    assert store.get_article(good.id).text


async def test_prefetch_checks_exclusions_in_retrieved_text_before_any_editorial_call():
    item = article(extracted=False)
    store = MemoryStore([item])
    collector = FakeCollector(store)
    collector.extract = AsyncMock(
        return_value=item.model_copy(
            update={
                "text": "cryptomonnaies " * 30,
                "extraction_status": "extracted",
            }
        )
    )
    model = InspectingModel()
    await pipeline(store, model, collector=collector).run(
        request(excluded_topics=["cryptomonnaies"])
    )
    assert model.previews == [] and model.summary_calls == 0


@pytest.mark.parametrize("mode", ["budget", "timeout", "network"])
async def test_prefetch_preserves_labeled_excerpts_without_retrying_failed_downloads(mode):
    item = article(extracted=False)
    store = MemoryStore([item])
    collector = FakeCollector(store)

    async def unavailable(item):
        collector.calls.append(item.id)
        if mode == "timeout":
            await asyncio.sleep(1)
        raise RetrievalError("Indisponible")

    collector.extract = unavailable
    model = InspectingModel([finalize_first])
    cover = await pipeline(
        store,
        model,
        collector=collector,
        max_fetches=0 if mode == "budget" else 1,
        prefetch_timeout=0.01,
    ).run(request())
    assert len(collector.calls) == (0 if mode == "budget" else 1)
    assert model.previews[0]["access"]["status"] == "excerpt_only"
    assert model.previews[0]["access"]["checked"] is (mode != "budget")
    assert cover.items[0].extraction_status == "excerpt"
    assert any("extrait" in text for text in cover.items[0].brief.caveats)


async def test_warm_text_is_not_downloaded_again():
    store = MemoryStore([article()])
    collector = FakeCollector(store)
    model = InspectingModel([finalize_first])
    await pipeline(store, model, collector=collector).run(request())
    assert collector.calls == []
    assert model.previews[0]["access"]["status"] == "full_text"


async def test_source_search_uses_only_provider_references_and_accepts_homepages_and_feeds():
    response = SimpleNamespace(
        status="completed",
        usage=None,
        model_dump=lambda: {
            "output": [
                {
                    "type": "web_search_call",
                    "status": "completed",
                    "action": {
                        "sources": [
                            {"url": "https://math.example/", "title": "Un blog de maths"},
                            {"url": "https://math.example/category/notes", "title": "Même site"},
                            {"url": "https://research.example/feed.xml", "title": "Autre carnet"},
                            {"url": "http://127.0.0.1/private", "title": "Local"},
                            {"url": "https://image.example/photo.png", "title": "Image"},
                        ]
                    },
                },
                {"type": "message", "content": [{"text": "https://invented.example/"}]},
            ],
        },
    )
    create = AsyncMock(return_value=response)
    model = SimpleNamespace(
        editor_model="test", client=SimpleNamespace(responses=SimpleNamespace(create=create))
    )
    budget = RunBudget({"web_model": 1}, 50_000)
    sources = await OpenAIWebSearch(model).search_sources(
        "mathématiques blogs pédagogiques", budget
    )
    assert [s.url for s in sources] == [
        "https://math.example/",
        "https://research.example/feed.xml",
    ]
    assert all(isinstance(s, SourceReference) for s in sources)
    assert budget.counts["hosted_web_calls"] == 1
    assert "SOURCES" in create.call_args.kwargs["input"]


async def test_source_probe_reuses_downloads_and_supports_a_blog_without_feed():
    fetcher = fetcher_for({ROOT: LISTING, "https://example.com/posts/first": story()})
    budget = RunBudget({"source_fetch": 5}, 50_000)
    kind, url, candidates = await source_article_candidates(fetcher, ROOT, budget)
    assert kind == "website" and url == ROOT
    assert len(candidates) == 1 and candidates[0].text
    assert fetcher.get.await_count == budget.counts["source_fetch"] == 2


class SourceSearch(FakeSearch):
    async def search_sources(self, query, budget, limit=3, *, context=None):
        self.queries.append(query)
        return [SourceReference("https://example.com/", "Carnet spécialisé")]


@pytest.mark.parametrize("pertinent", [True, False])
async def test_discovered_blog_supplies_current_cover_and_is_only_proposed_if_relevant(pertinent):
    store = MemoryStore()
    store.propose_source = lambda url, name, reason, origin, kind="rss": (
        proposals.append(
            {
                "url": url,
                "name": name,
                "kind": kind,
                "status": "proposed",
            }
        )
        or proposals[-1]
    )
    proposals = []
    collector = FakeCollector(store)
    collector.fetcher = fetcher_for(
        {
            "https://example.com/": Download(
                "https://example.com/",
                b'<link type="application/rss+xml" href="/feed">',
                "text/html",
            ),
            "https://example.com/feed": Download(
                "https://example.com/feed",
                FEED.replace(b"Python &amp; RSS", b"Architecture Python"),
                "application/rss+xml",
            ),
        }
    )

    class Model(ScriptedModel):
        async def screen(self, state, budget):
            plan = await super().screen(state, budget)
            for pick in plan.picks:
                pick.evergreen = True
                if not pertinent:
                    pick.matches_profile = False
            return plan

    model = Model(
        [decision("search_sources", query="Python blogs de praticiens")]
        + ([finalize_first] if pertinent else [])
    )
    req = request().model_copy(update={"discover_web": True, "discover_sources": True})
    cover = await pipeline(store, model, SourceSearch(), collector).run(req)
    assert bool(cover.items) is pertinent
    assert len(proposals) == int(pertinent)
    assert collector.fetcher.get.await_count == 2
    assert cover.usage["calls"]["search_web"] == 1
    assert cover.trace[0].action == "search_sources"
    if pertinent:
        assert cover.status == "complete"
        assert proposals[0]["status"] == "proposed"
        assert proposals[0]["url"] == "https://example.com/feed"
        item = store.get_article(cover.items[0].article_id)
        assert item.discovery["source_url"] == "https://example.com/feed"
        assert item.discovery["kind"] == "source_sample"
        assert item.discovery["provider"] == "openai_web_search"
    else:
        assert model.summary_calls == 0


async def test_source_search_rejects_excluded_domains_before_fetching():
    store = MemoryStore()
    collector = FakeCollector(store)
    collector.fetcher = SimpleNamespace(get=AsyncMock())
    runner = pipeline(store, ScriptedModel(), SourceSearch(), collector)
    req = request(excluded_sources=["example.com"]).model_copy(update={"discover_sources": True})
    outcome = await runner._act(decision("search_sources", query="Python"), req, set())
    assert outcome["added_ids"] == []
    collector.fetcher.get.assert_not_awaited()


async def test_model_can_search_sources_for_a_gap_but_no_web_search_when_needs_are_covered():
    model = OpenAILanguageModel("test", "test-summary", "test-editor", 1000)
    model._parse = AsyncMock(return_value=decision())
    state = {
        "candidates": [],
        "size": 18,
        "remaining_steps": 3,
        "remaining_summaries": 10,
        "web_search_enabled": True,
        "remaining_web_searches": 2,
        "source_search_enabled": True,
        "discover_sources": True,
        "remaining_source_proposals": 2,
        "remaining_article_imports": 10,
        "research": {"needed": True},
        "coverage": {"source_capacity_upper_bound": 0},
    }
    try:
        await model.decide(state, RunBudget({}, 50_000))
        schema = model._parse.call_args.args[3]
        schema.model_validate(decision("search_sources", query="blogs maths").model_dump())
        state.update(research={"needed": False}, coverage={"source_capacity_upper_bound": 18})
        await model.decide(state, RunBudget({}, 50_000))
        schema = model._parse.call_args.args[3]
        schema.model_validate(decision("finalize").model_dump())
        for action in ["search_web", "search_sources"]:
            with pytest.raises(ValidationError):
                schema.model_validate(decision(action, query="maths").model_dump())
    finally:
        await model.close()


async def test_unnecessary_web_action_is_rejected_without_spending_budget():
    runner = pipeline(MemoryStore([article()]), ScriptedModel([finalize_first]))
    await runner.run(request())
    with pytest.raises(ValueError, match="finalise sans recherche web"):
        await runner._act(decision("search_web", query="Python"), request(), set())
    assert not runner.budget.counts["search_web"]


async def test_source_search_skips_paid_provider_when_import_budget_is_exhausted():
    search = SourceSearch()
    runner = pipeline(MemoryStore(), ScriptedModel(), search, max_discovered_articles=0)
    req = request().model_copy(update={"discover_sources": True})
    with pytest.raises(BudgetExceeded, match="import"):
        await runner._find_source_articles("blogs Python", {}, req, set())
    assert search.queries == []


async def test_source_quota_shortage_keeps_research_available_despite_candidate_count():
    store = MemoryStore([article(1, source="same.example"), article(2, source="same.example")])
    model = InspectingModel()
    req = request(size=2).model_copy(update={"max_per_source": 1})
    await pipeline(store, model).run(req)
    state = model.states[0]
    assert len(state["candidates"]) == 2
    assert state["research"]["needed"]
    assert state["research"]["missing_slots"] == 1
