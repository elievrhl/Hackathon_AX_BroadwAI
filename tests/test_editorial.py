from collections import Counter
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from broadwai.llm import OpenAILanguageModel, RunBudget
from broadwai.models import EditorialPlan
from broadwai.network import RetrievalError
from broadwai.pricing import estimate_cost
from tests.fakes import FakeSearch, MemoryStore, ScriptedModel, article, decision, finalize_first
from tests.test_pipeline import pipeline, request


class PlannedModel(ScriptedModel):
    def __init__(self, plan, decisions):
        super().__init__(decisions)
        self.editorial_plan = plan
        self.plan_states = []

    async def plan(self, state, budget):
        budget.take("plan")
        self.plan_states.append(state)
        return self.editorial_plan


def plan_for(items, scores=None):
    return EditorialPlan(
        sections=["Économie", "Société", "Innovation"],
        picks=[
            {
                "article_id": a.id,
                "section": ["Économie", "Société", "Innovation"][i % 3],
                "score": scores[i] if scores else 80,
                "reason": "Un enjeu concret pour le lecteur",
                "matches_profile": True,
                "evergreen": False,
            }
            for i, a in enumerate(items)
        ],
        gaps=[],
        queries=[],
    )


def finalize_all(state):
    sections = state["editorial_plan"]["sections"]
    return decision(
        selections=[
            {
                "article_id": c["article_id"],
                "section": sections[i % 3],
                "reason": "Utile",
                "headline": c["title"],
            }
            for i, c in enumerate(state["candidates"][: state["size"]])
        ]
    )


async def test_editorial_rejection_happens_before_paid_summary():
    items = [article(1, title="Python concurrency"), article(2, title="Unrelated sport")]
    store = MemoryStore(items)
    model = PlannedModel(plan_for(items, [90, 25]), [finalize_first])
    cover = await pipeline(store, model).run(request())
    assert model.summary_calls == 1
    assert [c.article_id for c in cover.items] == [items[0].id]
    assert cover.diagnostics["editorial_plan"]["picks"][1]["score"] == 25


async def test_large_edition_keeps_two_candidates_per_requested_article():
    items = [article(i, title=f"Python angle {i}") for i in range(36)]
    model = PlannedModel(plan_for(items), [finalize_first])

    await pipeline(MemoryStore(items), model).run(request(size=18))

    assert model.plan_states[0]["selection_limit"] == 36


async def test_newspaper_eighteen_items_three_sections_with_compact_context():
    items = [article(i, title=f"Python angle{i} sujet{i} enjeu{i}") for i in range(18)]
    model = PlannedModel(plan_for(items), [finalize_all])
    cover = await pipeline(MemoryStore(items), model).run(request(size=18))
    assert cover.status == "complete"
    assert len(cover.items) == 18
    assert set(Counter(i.section for i in cover.items).values()) == {6}
    assert all(i.headline for i in cover.items)
    assert model.states[0]["coverage"]["source_capacity_upper_bound"] == 18
    context = model.states[0]["candidates"][0]
    assert "text" not in context and "key_points" not in context and "summary" in context
    assert "brief" in cover.diagnostics["candidates"][0]


async def test_short_cover_is_refused_until_editor_searches_for_replacements():
    first = article(1, title="Python architecture")
    second = article(2, title="Python performance")
    model = PlannedModel(
        plan_for([first]),
        [
            finalize_first,
            decision("search_web", query="Python performances récentes"),
            finalize_all,
        ],
    )
    search = FakeSearch([second])
    cover = await pipeline(MemoryStore([first]), model, search).run(request(size=2))
    assert cover.status == "complete" and len(cover.items) == 2
    assert "remplacements" in cover.trace[0].outcome["errors"][0]
    assert len(search.queries) == 1


async def test_failed_domain_does_not_consume_all_article_download_attempts():
    found = [article(i, source="broken.example", title=f"Python panne{i}") for i in range(3)]
    found.append(article(4, title="Python alternative"))
    from tests.fakes import FakeCollector

    class Collector(FakeCollector):
        async def extract(self, a):
            if a.source == "broken.example":
                self.calls.append(a.id)
                raise RetrievalError("TLS unavailable")
            return await super().extract(a)

    store = MemoryStore()
    collector = Collector(store)
    model = ScriptedModel([decision("search_web", query="Python"), finalize_first])
    cover = await pipeline(store, model, FakeSearch(found), collector).run(request())
    assert len(collector.calls) == 3
    assert found[2].id not in collector.calls
    assert cover.items[0].article_id == found[3].id


async def test_one_rubric_is_not_a_complete_newspaper():
    items = [article(i, title=f"Python theme{i} angle{i}") for i in range(15)]

    def bad_finalize(state):
        d = finalize_all(state)
        for s in d.selections:
            s.section = "Tout"
        return d

    model = PlannedModel(plan_for(items), [bad_finalize])
    cover = await pipeline(MemoryStore(items), model, max_agent_steps=1).run(request(size=15))
    assert cover.status == "fallback"
    assert any("rubriques" in e for e in cover.trace[-1].outcome["errors"])


async def test_final_schema_disallows_unknown_identifiers_before_generation():
    model = OpenAILanguageModel("test", "nano-test", "mini-test", 1000)
    model._parse = AsyncMock(return_value=decision())
    try:
        await model.decide({"candidates": [{"article_id": "known"}]}, RunBudget({}, 50000))
        schema = model._parse.call_args.args[3]
        invalid = decision(
            selections=[{"article_id": "invented", "section": "Test", "reason": "Test"}]
        )
        with pytest.raises(ValidationError):
            schema.model_validate(invalid.model_dump())
    finally:
        await model.close()


def test_cost_estimate_accounts_for_cache_tools_and_unknown_usage():
    call = {
        "model": "gpt-5.4-mini",
        "usage": {
            "input_tokens": 1000,
            "cached_input_tokens": 400,
            "output_tokens": 200,
        },
    }
    assert estimate_cost([call], 2)["estimated_usd"] == pytest.approx(0.02138)
    assert estimate_cost([{"model": "unknown"}])["estimated_usd"] is None


async def test_search_screen_rejects_noise_without_summarizing():
    class RejectingModel(ScriptedModel):
        async def screen(self, state, budget):
            budget.take("screen")
            return EditorialPlan(sections=["Économie"], picks=[], gaps=[], queries=[])

    store = MemoryStore([article(1, title="Python random result")])
    model = RejectingModel()
    runner = pipeline(store, model)
    outcome = await runner._act(decision("search_catalog", query="Python"), request(), set())
    assert outcome["added_ids"] == [] and model.summary_calls == 0


async def test_editor_cannot_finalize_when_known_capacity_is_insufficient():
    model = OpenAILanguageModel("test", "nano-test", "mini-test", 1000)
    model._parse = AsyncMock(return_value=decision("search_web", query="Python"))
    try:
        await model.decide(
            {
                "candidates": [],
                "size": 18,
                "remaining_steps": 3,
                "remaining_summaries": 10,
                "remaining_web_searches": 1,
                "web_search_enabled": True,
                "remaining_catalog_searches": 0,
                "coverage": {"source_capacity_upper_bound": 5},
            },
            RunBudget({}, 50000),
        )
        schema = model._parse.call_args.args[3]
        with pytest.raises(ValidationError):
            schema.model_validate(decision().model_dump())
    finally:
        await model.close()


async def test_undated_web_result_is_not_presented_as_current_news():
    item = article().model_copy(
        update={"published_at": None, "discovery": {"provider": "openai_web_search"}}
    )
    model = ScriptedModel()
    cover = await pipeline(MemoryStore([item]), model).run(request())
    assert cover.items == [] and model.summary_calls == 1


async def test_high_score_cannot_override_mismatch_with_explicit_profile_context():
    paris = article(1, title="Expositions culturelles Paris")
    plan = plan_for([paris], [95])
    plan.picks[0].matches_profile = False
    model = PlannedModel(plan, [])
    cover = await pipeline(MemoryStore([paris]), model).run(
        request(notes="Singapour et Asie du Sud-Est")
    )
    assert not cover.items
    assert model.summary_calls == 0


async def test_search_screen_rejects_profile_mismatch_before_summary():
    class ContextModel(ScriptedModel):
        async def screen(self, state, budget):
            result = await super().screen(state, budget)
            for pick in result.picks:
                pick.matches_profile = False
                pick.score = 95
            return result

    model = ContextModel()
    runner = pipeline(MemoryStore([article()]), model)
    outcome = await runner._act(
        decision("search_catalog", query="Python"), request(notes="Singapour"), set()
    )
    assert not outcome["added_ids"] and model.summary_calls == 0


@pytest.mark.parametrize("age", [None, 180])
async def test_old_or_undated_essay_requires_explicit_evergreen_selection(age):
    from datetime import timedelta

    from broadwai.models import utcnow

    essay = article(title="Culture Singapore independent essay").model_copy(
        update={
            "published_at": utcnow() - timedelta(days=age) if age else None,
            "discovery": {"provider": "openai_web_search"},
        }
    )
    plan = plan_for([essay])
    plan.picks[0].evergreen = True
    model = PlannedModel(plan, [finalize_all])
    cover = await pipeline(MemoryStore([essay]), model).run(request())
    assert len(cover.items) == 1
    assert cover.items[0].reading_kind == "evergreen"
    assert cover.items[0].published_at == essay.published_at
    assert model.states[0]["candidates"][0]["reading_kind"] == "evergreen"


async def test_old_news_cannot_be_laundered_as_an_evergreen_essay():
    from datetime import timedelta

    from broadwai.models import utcnow

    story = article().model_copy(update={"published_at": utcnow() - timedelta(days=180)})
    plan = plan_for([story])
    plan.picks[0].evergreen = True

    class NewsModel(PlannedModel):
        async def summarize(self, item, budget):
            brief = await super().summarize(item, budget)
            return brief.model_copy(update={"content_type": "news"})

    cover = await pipeline(MemoryStore([story]), NewsModel(plan, [])).run(request())
    assert not cover.items
    assert any(
        e.get("reason") == "Actualité périmée ou non datée" for e in cover.diagnostics["events"]
    )


async def test_two_discoveries_can_supply_eighteen_articles_to_a_cold_catalogue():
    class BroadSearch(FakeSearch):
        async def search(self, query, budget, limit=5, *, context=None):
            self.queries.append((query, context, limit))
            start = 0 if len(self.queries) == 1 else 12
            return self.articles[start : start + limit]

    class BroadModel(PlannedModel):
        async def screen(self, state, budget):
            result = await super().screen(state, budget)
            for index, pick in enumerate(result.picks):
                pick.section = state["sections"][index % 3]
            return result

    items = [
        article(i, title=f"Python sujet{i} angle{i} découverte{i}").model_copy(
            update={"excerpt": f"Analyse détaillée du sujet {i}, résultats et expérience {i}. " * 3}
        )
        for i in range(20)
    ]
    search = BroadSearch(items)
    model = BroadModel(
        plan_for([]),
        [
            decision("search_web", query="Python site:large.example OR site:paper.example"),
            decision("search_web", query="Python independent practitioner essays"),
            finalize_all,
        ],
    )
    cover = await pipeline(MemoryStore(), model, search).run(request(size=18))
    assert cover.status == "complete" and len(cover.items) == 18, [
        event.model_dump() for event in cover.trace
    ]
    assert len(search.queries) == 2
    assert search.queries[0][0] == "Python"
    assert search.queries[1][1]["strategy"] == "independent"
    assert "profile" in search.queries[0][1]
    assert cover.trace[0].outcome["requested_query"].startswith("Python site:")
    assert cover.trace[0].outcome["query"] == "Python"
    assert cover.usage["calls"]["summary"] <= 24
