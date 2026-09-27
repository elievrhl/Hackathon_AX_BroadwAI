"""Deterministic orchestration fixtures, not a paid model-quality benchmark."""

from unittest.mock import AsyncMock

import pytest

from broadwai.broadening import exploration_limit, next_angle, research_angles
from broadwai.llm import ModelError
from broadwai.models import EditorialIntent, Interest, SearchAngle
from tests.fakes import FakeSearch, MemoryStore, article
from tests.test_pipeline import pipeline, request
from tests.test_structural_pipeline import DossierModel, compose, dossier, plan


def broad_plan(items, focused=None):
    value = plan(items)
    value.contract_version = 4
    for pick in value.picks[len(items) if focused is None else focused :]:
        pick.exploration = True
        pick.section = "Exploration"
        pick.exploration_reason = "Les méthodes de preuve éclairent la vérification du logiciel."
    return value


def articles(count):
    return [article(i, title=f"Python sujet{i} angle{i} exemple{i}") for i in range(count)]


def angle(query, scope="depth", need_id="need-1"):
    return SearchAngle(need_id=need_id, query=query, scope=scope, connection="Méthode du domaine")


def test_exploration_never_exceeds_quarter_of_target_or_result():
    for size in range(1, 21):
        for focused in range(size + 1):
            limit = exploration_limit(size, focused)
            assert limit * 4 <= size
            assert limit * 4 <= focused + limit
            assert focused + limit <= size
            assert exploration_limit(size, focused, False) == 0
    assert exploration_limit(18, 7) == 2


def test_angles_preserve_known_needs_and_exclusive_scope():
    value = broad_plan([])
    value.search_angles = [
        angle("Calcul formel", "adjacent"),
        angle("Unknown", need_id="bad"),
        angle("Python architecture"),
    ]
    intent = {
        "needs": [{"id": "need-1", "query": "Python", "topic": "Python"}],
        "allow_adjacent": False,
    }
    result = research_angles(value, intent, [])
    assert [a["query"] for a in result] == ["Python architecture", "Python"]


def test_queries_rotate_even_when_switching_external_tools():
    angles = [
        angle("astronomie missions récentes", "direct").model_dump(),
        angle("missions récentes astronomie", "direct").model_dump(),
        angle("spectroscopie stellaire principes").model_dump(),
    ]
    history = [
        {
            "action": "search_sources",
            "query": "astronomie missions récentes en français",
            "added": 0,
        }
    ]
    selected = next_angle(angles, history, "search_web", adjacent_allowed=False, french_only=True)
    assert selected["query"] == "spectroscopie stellaire principes en français"
    history.append({"action": "search_web", "query": selected["query"], "added": 0})
    assert next_angle(angles, history, "search_web", adjacent_allowed=False) is None


def test_empty_catalogue_does_not_preclude_external_search():
    angles = [angle("astrophysique", "direct").model_dump()]
    history = [{"action": "search_catalog", "query": "astrophysique", "added": 0}]
    assert (
        next_angle(angles, history, "search_web", adjacent_allowed=False)["query"]
        == "astrophysique"
    )


async def test_open_profile_prepares_only_bounded_adjacent_reserve_and_labels_it():
    items = articles(18)
    model = DossierModel(broad_plan(items, focused=7), [compose])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(request(size=18))
    assert len(cover.items) == 9
    assert model.summary_calls == 9
    adjacent = [i for i in cover.items if i.selection_kind == "exploration"]
    assert len(adjacent) == 2
    assert all(i.section == "Exploration" and i.exploration_reason for i in adjacent)
    assert model.states[0]["exploration_limit"] == 2


async def test_actual_composition_not_candidate_pool_determines_adjacent_share():
    items = articles(18)

    def drop_focused(state):
        choice = compose(state)
        choice.selections = [choice.selections[0], *choice.selections[7:]]
        return choice

    model = DossierModel(broad_plan(items, focused=7), [drop_focused])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(request(size=18))
    assert len(cover.items) == 1
    assert cover.items[0].selection_kind == "focused"


async def test_adjacent_alone_cannot_become_the_edition():
    items = articles(6)
    model = DossierModel(broad_plan(items, focused=0), [compose])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(request(size=18))
    assert not cover.items
    assert model.summary_calls == 0


async def test_fallback_does_not_publish_an_unreviewed_adjacent_bridge():
    items = articles(9)
    model = DossierModel(broad_plan(items, focused=7), [])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(request(size=18))
    assert cover.status == "fallback"
    assert len(cover.items) == 7
    assert all(i.selection_kind == "focused" for i in cover.items)


@pytest.mark.parametrize("interpret_failed", [False, True])
async def test_exclusive_or_uninterpreted_notes_do_not_open_adjacent_topics(interpret_failed):
    items = articles(9)
    model = DossierModel(broad_plan(items, focused=7), [compose])
    intent = EditorialIntent(
        needs=[
            {"topic": "Python", "query": "Python", "priority": "primary", "level": "intermediate"}
        ],
        allow_adjacent=False,
    )
    model.interpret = (
        AsyncMock(side_effect=ModelError("unavailable"))
        if interpret_failed
        else AsyncMock(return_value=intent)
    )
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(
        request(size=18, notes="Uniquement Python, aucun thème voisin")
    )
    assert len(cover.items) == 7
    assert all(i.selection_kind == "focused" for i in cover.items)
    assert model.plan_states[0]["exploration_allowed"] is False


async def test_unused_interest_slots_are_redistributed_not_lost():
    items = articles(14)
    value = broad_plan(items)
    for pick in value.picks[-2:]:
        pick.interest_id = "interest-2"
        pick.matched_need = "need-2"
    req = request(size=18)
    req.profile.interests.append(Interest(topic="Mathématiques"))
    model = DossierModel(value, [compose])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(req)
    assert len(cover.items) == 14  # Before: 9 from the first topic + 2 from the second.
    assert set(i.article_id for i in cover.items) == {i.id for i in items}
    assert model.states[0]["editorial_intent"]["interest_balance"]["maximum_is_target"]


async def test_within_domain_depth_is_not_capped_as_adjacent():
    items = articles(18)
    model = DossierModel(broad_plan(items), [compose])
    search = FakeSearch()
    req = request(size=18).model_copy(update={"discover_web": True})
    cover = await pipeline(MemoryStore(items), model, search).run(req)
    assert len(cover.items) == 18
    assert all(i.selection_kind == "focused" for i in cover.items)
    assert not search.queries
    assert cover.usage["calls"]["plan"] == cover.usage["calls"]["editor"] == 1


async def test_controller_changes_angles_within_existing_search_budget():
    items = articles(1)
    value = broad_plan(items)
    value.search_angles = [
        angle("Python", "direct"),
        angle("algorithmes concurrents"),
        angle("histoire langages informatiques"),
    ]
    model = DossierModel(value, [compose])
    search = FakeSearch()
    runner = pipeline(MemoryStore(items), model, search)
    cover = await runner.run(request(size=18).model_copy(update={"discover_web": True}))
    assert search.queries == ["algorithmes concurrents", "histoire langages informatiques"]
    assert cover.usage["calls"]["search_web"] == 2
    assert cover.usage["calls"]["editor"] == 1
    assert all(
        e.outcome.get("search_angle") for e in cover.trace if e.outcome.get("actor") == "controller"
    )


async def test_web_screen_can_add_a_bounded_adjacent_reserve():
    items = articles(7)
    found = article(100, title="Python preuve formelle des programmes")
    model = DossierModel(broad_plan(items), [compose])

    async def screen(state, budget):
        budget.take("screen")
        assert state["exploration_allowed"] is True
        return broad_plan([found], focused=0)

    model.screen = screen
    cover = await pipeline(MemoryStore(items), model, FakeSearch([found])).run(
        request(size=18).model_copy(update={"discover_web": True})
    )
    assert len(cover.items) == 8
    assert cover.items[-1].article_id == found.id
    assert cover.items[-1].selection_kind == "exploration"


async def test_catalogue_beyond_old_3000_limit_does_not_expand_paid_preview():
    items = articles(3000)
    found = article(4000, title="Astronomie spectroscopie étoiles galaxies")
    store = MemoryStore([*items, found])
    req = request()
    req.profile.interests = [Interest(topic="Astronomie")]
    model = DossierModel(broad_plan([found]), [compose])
    cover = await pipeline(store, model).run(req)
    assert [i.article_id for i in cover.items] == [found.id]
    assert len(model.plan_states[0]["candidates"]) <= 96
    assert model.summary_calls == 1


@pytest.mark.parametrize("blocked", ["topic", "source", "language", "off_profile", "risk"])
async def test_widening_keeps_hard_content_guards(blocked):
    items = articles(8)
    items[-1] = items[-1].model_copy(
        update={"title": "Python astrologie prétendument scientifique"}
    )
    value = broad_plan(items, focused=7)
    req = request(size=18)
    if blocked == "topic":
        req.profile.excluded_topics = ["astrologie"]
    elif blocked == "source":
        req.profile.excluded_sources = [items[-1].source]
    elif blocked == "language":
        req.profile.languages = ["fr"]
        items[-1] = items[-1].model_copy(update={"language": "de"})
    elif blocked == "off_profile":
        value.picks[-1].matches_profile = False
    model = DossierModel(value, [compose])
    original = model.summarize

    async def summarize(item, budget):
        brief = await original(item, budget)
        return (
            brief.model_copy(update={"dossier": dossier(central_risk=True)})
            if blocked == "risk" and item.id == items[-1].id
            else brief
        )

    model.summarize = summarize
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(req)
    assert len(cover.items) == 7
    assert items[-1].id not in {i.article_id for i in cover.items}


async def test_soft_interest_quota_keeps_hard_source_quota():
    items = [
        article(i, title=f"Python sujet{i} angle{i}", source="unique.example") for i in range(12)
    ]
    model = DossierModel(broad_plan(items), [compose])
    cover = await pipeline(MemoryStore(items), model, max_web_searches=0).run(request(size=18))
    assert len(cover.items) == 3
