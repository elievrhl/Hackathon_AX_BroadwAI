from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from broadwai.editorial import compact_candidate, preview
from broadwai.llm import BudgetExceeded, OpenAILanguageModel, RunBudget
from broadwai.models import Candidate, ReadingDossier, utcnow
from broadwai.ranking import rank
from tests.fakes import FakeSearch, MemoryStore, article, decision
from tests.test_editorial import PlannedModel, plan_for
from tests.test_pipeline import pipeline, request


def dossier(**updates):
    return ReadingDossier(
        **{
            "contribution": "Comprendre une méthode concrète",
            "angle": "Comparaison par exemple",
            "prerequisites": "Notions de programmation",
            "integrity": "clear",
            "support": "method",
            "central_risk": False,
            "temporal_kind": "evergreen",
            "temporal_dependency": None,
            "obsolete_explicit": False,
            **updates,
        }
    )


def plan(items, scores=None):
    value = plan_for(items, scores)
    value.contract_version = 3
    for pick in value.picks:
        pick.matched_need = "need-1"
        pick.interest_id = "interest-1"
        pick.temporal_kind = "evergreen"
        pick.evergreen = True
    return value


def compose(state):
    return decision(
        selections=[
            {
                "article_id": c["article_id"],
                "section": "Une rubrique réorganisée",
                "reason": "Méthode répondant au besoin de programmation",
                "headline": c["title"],
                "matched_need": "need-1",
                "role": "lead" if i == 0 else "reading",
                "story_key": c["article_id"],
            }
            for i, c in enumerate(state["candidates"][: state["size"]])
        ]
    )


class DossierModel(PlannedModel):
    details = dossier()

    async def summarize(self, item, budget):
        brief = await super().summarize(item, budget)
        return brief.model_copy(update={"dossier": self.details, "headline": item.title[:180]})


async def test_short_selection_and_new_sections_do_not_force_research_or_filler():
    items = [article(i, title=f"Python sujet{i} angle{i} exemple{i}") for i in range(17)]
    model = DossierModel(plan(items), [compose])
    search = FakeSearch()
    req = request(size=18).model_copy(update={"discover_web": True})
    cover = await pipeline(MemoryStore(items), model, search).run(req)
    assert len(cover.items) == 17 and cover.status == "partial"
    assert cover.usage["calls"]["editor"] == 1
    assert not search.queries
    assert not [e for e in cover.trace if e.action.startswith("search")]
    assert all(i.section == "Une rubrique réorganisée" for i in cover.items)


async def test_low_score_is_ordering_not_hard_rejection_but_off_profile_still_blocks():
    items = [article(1), article(2)]
    value = plan(items, [25, 95])
    value.picks[1].matches_profile = False
    model = DossierModel(value, [compose])
    cover = await pipeline(MemoryStore(items), model).run(request())
    assert [i.article_id for i in cover.items] == [items[0].id]
    assert model.summary_calls == 1


@pytest.mark.parametrize(
    "details,age,accepted",
    [
        (dossier(), 365 * 40, True),
        (dossier(integrity="fragmentary"), 4, True),
        (dossier(temporal_dependency="Exemple sous Python 3.10"), 100, True),
        (dossier(integrity="unusable"), 0, False),
        (dossier(central_risk=True), 0, False),
        (dossier(obsolete_explicit=True), 0, False),
        (dossier(temporal_kind="news"), 100, False),
        (dossier(temporal_kind="research"), 400, False),
    ],
)
async def test_integrity_risk_and_live_age_are_independent(details, age, accepted):
    item = article().model_copy(update={"published_at": utcnow() - timedelta(days=age)})
    model = DossierModel(plan([item]), [compose])
    model.details = details
    cover = await pipeline(MemoryStore([item]), model, max_web_searches=0).run(request())
    assert bool(cover.items) is accepted


async def test_progressive_preparation_keeps_reserves_without_summarizing_all():
    items = [article(i, title=f"Python sujet{i} angle{i} exemple{i}") for i in range(36)]
    model = DossierModel(plan(items), [compose])
    runner = pipeline(MemoryStore(items), model)
    cover = await runner.run(request(size=18))
    assert model.summary_calls == 24
    assert len(cover.items) == 18
    assert len(runner.reserve_pool) == 36


async def test_controller_searches_without_editor_routing_and_respects_permission():
    item = article()
    model = DossierModel(plan([item]), [compose])
    search = FakeSearch()
    runner = pipeline(MemoryStore([item]), model, search)
    cover = await runner.run(request(size=18))  # No web permission.
    assert not search.queries
    assert cover.usage["calls"]["editor"] == 1
    assert any(e.outcome.get("actor") == "controller" for e in cover.trace)
    assert all(e.action != "search_web" for e in cover.trace)
    runner.budget.counts["screen"] = runner.budget.limits["screen"]
    with pytest.raises(BudgetExceeded):
        await runner._act(decision("search_web", query="Python"), request(), set())
    assert not search.queries


async def test_compact_composer_schema_omits_copied_headline_and_search_actions():
    model = OpenAILanguageModel("test-key", "test", "test", 1000)

    async def parse(**kwargs):
        schema = kwargs["text_format"]
        choice = schema.model_fields["selections"].annotation.__args__[0]
        assert "headline" not in choice.model_fields
        assert schema.model_fields["action"].annotation.__args__ == ("finalize", "read_article")
        result = schema.model_validate(
            {
                "action": "finalize",
                "query": None,
                "article_id": None,
                "title": "Le titre",
                "justification": "Une lecture suffit",
                "selections": [
                    {
                        "article_id": "known",
                        "section": "Méthodes",
                        "reason": "Utile",
                        "matched_need": "need-1",
                        "role": "lead",
                        "story_key": "Méthode A",
                    }
                ],
            }
        )
        return SimpleNamespace(status="completed", output_parsed=result, usage=None)

    model.client.responses.parse = AsyncMock(side_effect=parse)
    try:
        result = await model.decide(
            {
                "composition_mode": True,
                "remaining_steps": 3,
                "editorial_intent": {"needs": [{"id": "need-1"}]},
                "candidates": [{"article_id": "known", "title": "Original title"}],
            },
            RunBudget({"editor": 1}, 50000),
        )
        assert result.selections[0].headline == "Original title"
    finally:
        await model.close()


async def test_controller_can_discover_articles_for_a_real_gap():
    first = article(1, title="Python méthode architecture")
    found = article(2, title="Python pratique performances")
    model = DossierModel(plan([first]), [compose])
    search = FakeSearch([found])
    req = request(size=3).model_copy(update={"discover_web": True})
    cover = await pipeline(MemoryStore([first]), model, search).run(req)
    assert search.queries
    assert any(
        e.action == "search_web" and e.outcome.get("actor") == "controller" for e in cover.trace
    )
    assert cover.usage["calls"]["editor"] == 1


async def test_dossier_roundtrip_in_postgres_and_legacy_brief_stays_readable(pg_store):
    item = article()
    model = DossierModel(plan([item]), [compose])
    brief = await model.summarize(item, RunBudget({"summary": 1}, 50000))
    pg_store.put_article(item)
    pg_store.put_brief(item, "brief-v7-test", brief)
    assert pg_store.get_brief(item, "brief-v7-test") == brief
    old = brief.model_copy(update={"dossier": None})
    pg_store.put_brief(item, "brief-v6-test", old)
    assert pg_store.get_brief(item, "brief-v6-test") == old


async def test_preview_uses_retrieved_text_and_composer_sees_all_concrete_limits():
    item = article().model_copy(update={"text": "Texte intégral utile " * 100})
    assert preview(rank([item], request().profile)[0])["excerpt"] == item.text[:1400]
    model = DossierModel(plan([item]), [compose])
    brief = await model.summarize(item, RunBudget({"summary": 1}, 50000))
    brief.caveats = ["Condition A", "Condition B", "Limite importante C"]
    candidate = Candidate(
        article_id=item.id,
        title=item.title,
        url=item.url,
        source=item.source,
        published_at=item.published_at,
        extraction_status=item.extraction_status,
        score=1,
        matched_interests=[],
        brief=brief,
    )
    context = compact_candidate(candidate)
    assert context["dossier"]["contribution"] == brief.dossier.contribution
    assert context["caveats"] == brief.caveats
    assert not {"summary", "headline", "validity"} & context.keys()
