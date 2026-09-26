from datetime import timedelta

import pytest

from broadwai.models import utcnow
from tests.fakes import FakeSearch, MemoryStore, article, decision
from tests.test_editorial import PlannedModel, finalize_all, plan_for
from tests.test_pipeline import pipeline, request


def exploration_plan(focused, adjacent):
    plan = plan_for([*focused, *adjacent])
    for pick in plan.picks[len(focused) :]:
        pick.exploration = True
        pick.section = "Exploration"
        pick.exploration_reason = "Votre intérêt pour Python mène au design des outils de pensée."
    return plan


async def test_exploration_fills_only_missing_slots_with_a_visible_connection():
    focused = article(1, title="Python architecture pratique")
    adjacent = [
        article(2, title="Histoire des interfaces graphiques"),
        article(3, title="Sciences cognitives et outils de pensée"),
    ]
    model = PlannedModel(exploration_plan([focused], adjacent), [finalize_all])
    store = MemoryStore([focused, *adjacent])
    cover = await pipeline(store, model).run(request(size=2))
    assert cover.status == "complete"
    assert [item.selection_kind for item in cover.items] == ["focused", "exploration"]
    assert cover.items[1].section == "Exploration"
    assert "Python" in cover.items[1].exploration_reason
    assert model.summary_calls == 2  # The unused reserve is never summarized.
    assert model.states[0]["focused_capacity"] == 1
    assert model.states[0]["exploration_allowed"] is True
    assert store.get_cover(cover.id).items[1].selection_kind == "exploration"


async def test_full_direct_selection_never_spends_on_exploration():
    focused = [article(1, title="Python concurrence"), article(2, title="Python générateurs")]
    adjacent = article(3, title="Histoire des interfaces")
    plan = exploration_plan(focused, [adjacent])
    plan.picks.insert(0, plan.picks.pop())  # Even a highly ranked reserve cannot displace a match.
    model = PlannedModel(plan, [finalize_all])
    cover = await pipeline(MemoryStore([*focused, adjacent]), model).run(request(size=2))
    assert cover.status == "complete"
    assert all(item.selection_kind == "focused" for item in cover.items)
    assert model.summary_calls == 2
    assert model.states[0]["exploration_allowed"] is False


@pytest.mark.parametrize("rejection", ["low_quality", "context_mismatch", "missing_connection"])
async def test_exploration_preserves_editorial_requirements_before_summary(rejection):
    adjacent = article(title="Histoire des interfaces")
    plan = exploration_plan([], [adjacent])
    if rejection == "low_quality":
        plan.picks[0].score = 69
    elif rejection == "context_mismatch":
        plan.picks[0].matches_profile = False
    else:
        plan.picks[0].exploration_reason = " "
    model = PlannedModel(plan, [])
    cover = await pipeline(MemoryStore([adjacent]), model).run(request())
    assert not cover.items
    assert model.summary_calls == 0


async def test_direct_web_discovery_precedes_exploration_and_passes_context():
    focused = article(1, title="Python architecture pratique")
    adjacent = article(2, title="Design des outils de pensée")

    class Search(FakeSearch):
        async def search(self, query, budget, limit=5, *, context=None):
            self.queries.append(context)
            return [] if len(self.queries) == 1 else [adjacent]

    class Model(PlannedModel):
        async def screen(self, state, budget):
            budget.take("screen")
            assert state["exploration_allowed"] is True
            return exploration_plan([], [adjacent])

    model = Model(
        plan_for([focused]),
        [
            decision("search_web", query="Python recherches récentes"),
            decision("search_web", query="design outils pensée sciences cognitives"),
            finalize_all,
        ],
    )
    search = Search()
    req = request(size=2)
    req.discover_web = True
    cover = await pipeline(MemoryStore([focused]), model, search).run(req)
    assert cover.status == "complete"
    assert [context["exploration_allowed"] for context in search.queries] == [False, True]
    assert cover.items[1].selection_kind == "exploration"
    assert cover.items[1].section == "Exploration"


async def test_exploration_respects_shared_source_quotas_and_fallback_label():
    focused = article(1, title="Python architecture pratique", source="same.example")
    blocked = article(2, title="Histoire des interfaces", source="same.example")
    adjacent = article(3, title="Sciences cognitives et outils")
    model = PlannedModel(exploration_plan([focused], [blocked, adjacent]), [])
    req = request(size=2)
    req.max_per_source = 1
    cover = await pipeline(MemoryStore([focused, blocked, adjacent]), model).run(req)
    assert cover.status == "fallback"
    assert [item.article_id for item in cover.items] == [focused.id, adjacent.id]
    assert cover.items[1].section == "Exploration"
    assert cover.items[1].selection_kind == "exploration"


async def test_exploration_cannot_replace_direct_candidates_in_final_selection():
    focused = article(1, title="Python architecture pratique")
    adjacent = article(2, title="Histoire des interfaces")
    replacement = article(3, title="Python générateurs")
    runner = pipeline(
        MemoryStore([focused, adjacent, replacement]),
        PlannedModel(exploration_plan([focused], [adjacent]), []),
    )
    req = request(size=2)
    await runner.run(req)
    extra_plan = plan_for([replacement])
    runner.picks[replacement.id] = extra_plan.picks[0]
    from broadwai.ranking import Ranked

    await runner._prepare(Ranked(replacement, 1, []), req, set())
    selected, removed = runner._allocate(runner._available_selections(), req)
    assert [item.article_id for item in selected] == [focused.id, replacement.id]
    assert any(row["reason"] == "Exploration réservée aux places manquantes" for row in removed)


@pytest.mark.parametrize(
    ("age", "evergreen", "content_type", "accepted"),
    [
        (2, False, "news", True),
        (8, False, "news", False),
        (None, False, "news", False),
        (180, True, "analysis", True),
        (366, True, "analysis", True),
        (3650, True, "analysis", True),
        (None, True, "analysis", True),
        (8, True, "news", False),
        (2, True, "news", True),
        (-2, True, "analysis", False),
    ],
)
async def test_current_news_and_evergreen_have_distinct_age_limits(
    age, evergreen, content_type, accepted
):
    item = article().model_copy(
        update={
            "published_at": utcnow() - timedelta(days=age) if age is not None else None,
        }
    )
    plan = plan_for([item])
    plan.picks[0].evergreen = evergreen

    class Model(PlannedModel):
        async def summarize(self, article, budget):
            brief = await super().summarize(article, budget)
            return brief.model_copy(update={"content_type": content_type})

    model = Model(plan, [finalize_all] if accepted else [])
    cover = await pipeline(MemoryStore([item]), model).run(request())
    assert bool(cover.items) is accepted
    if accepted:
        expected = "evergreen" if evergreen and content_type != "news" else "current"
        assert cover.items[0].reading_kind == expected
        assert model.states[0]["candidates"][0]["reading_kind"] == expected
