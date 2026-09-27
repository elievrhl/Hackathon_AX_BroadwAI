from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from broadwai.llm import BudgetExceeded, OpenAILanguageModel, RunBudget
from broadwai.models import (
    Article,
    Brief,
    EditorialIntent,
    Profile,
    ReadingValidity,
    Selection,
    utcnow,
)
from broadwai.ranking import rank
from tests.fakes import MemoryStore, ScriptedModel, article, decision, finalize_first
from tests.test_editorial import PlannedModel, finalize_all, plan_for
from tests.test_pipeline import pipeline, request


def response(tokens):
    return SimpleNamespace(
        status="completed", usage=SimpleNamespace(input_tokens=tokens, output_tokens=0)
    )


@pytest.mark.parametrize("language", ["français", "French", "fr-FR", "fr_FR", "fra"])
async def test_language_names_and_regional_codes_share_the_same_filter(language):
    item = Article.model_validate({**article().model_dump(), "language": language})
    profile = Profile.model_validate(
        {**request().profile.model_dump(), "languages": [language, "fr"]}
    )
    brief = await ScriptedModel().summarize(item, RunBudget({"summary": 1}, 1000))
    brief = Brief.model_validate({**brief.model_dump(), "language": language})
    assert item.language == brief.language == "fr"
    assert profile.languages == ["fr"]
    assert len(rank([item], profile)) == 1
    foreign = Article.model_validate({**item.model_dump(), "language": "English"})
    assert foreign.language == "en"
    assert rank([foreign], profile) == []


def test_parallel_reservations_are_reconciled_once_even_out_of_order():
    budget = RunBudget({"summary": 3}, 1000)
    budget.take("summary", 400)
    first = budget.start_call("summary", "test", {}, 400)
    budget.take("summary", 400)
    second = budget.start_call("summary", "test", {}, 400)
    budget.end_call(second, response(80))
    assert budget.remaining_tokens == 520
    budget.end_call(first, response(120))
    budget.end_call(first, response(120))
    assert budget.remaining_tokens == 800
    assert budget.reserved_tokens == 0
    assert budget.input_tokens == 200
    assert budget.report()["reserved_token_estimate"] == 800


def test_unknown_usage_keeps_a_conservative_hold_and_final_reserve_is_protected():
    budget = RunBudget({"summary": 3, "editor": 2}, 1000, final_reserve=300)
    budget.take("summary", 600)
    marker = budget.start_call("summary", "test", {}, 600)
    budget.end_call(marker, error="Timeout")
    assert budget.remaining_tokens == 400
    with pytest.raises(BudgetExceeded):
        budget.take("summary", 150)
    assert budget.counts["summary"] == 1
    budget.take("editor", 350, final=True)
    assert budget.remaining_tokens == 50


@pytest.mark.parametrize(
    "status,accepted", [("durable", True), ("outdated", False), ("uncertain", False)]
)
async def test_decades_old_essays_depend_on_validity_not_age(status, accepted):
    item = article(title="Une histoire des instruments scientifiques").model_copy(
        update={"published_at": utcnow() - timedelta(days=365 * 40)}
    )
    plan = plan_for([item])
    plan.picks[0].evergreen = True
    plan.picks[0].temporal_kind = "evergreen"

    class Model(PlannedModel):
        async def summarize(self, item, budget):
            brief = await super().summarize(item, budget)
            return brief.model_copy(
                update={
                    "headline": "Histoire des instruments scientifiques",
                    "validity": ReadingValidity(
                        kind="evergreen",
                        status=status,
                        reason="Évaluation de l'apport historique du texte",
                    ),
                }
            )

    cover = await pipeline(MemoryStore([item]), Model(plan, [finalize_all])).run(request())
    assert bool(cover.items) is accepted
    if accepted:
        assert cover.items[0].reading_kind == "evergreen"
        assert cover.items[0].published_at == item.published_at
    else:
        assert "Validité" in cover.diagnostics["rejected"][0]["reason"]


@pytest.mark.parametrize(
    "age,kind,accepted",
    [(80, "research", True), (400, "research", False), (80, "news", False), (80, "event", False)],
)
async def test_old_research_is_dated_and_not_turned_into_today_news(age, kind, accepted):
    item = article().model_copy(update={"published_at": utcnow() - timedelta(days=age)})
    plan = plan_for([item])
    plan.picks[0].temporal_kind = kind

    class Model(PlannedModel):
        async def summarize(self, item, budget):
            return (await super().summarize(item, budget)).model_copy(
                update={
                    "validity": ReadingValidity(
                        kind=kind,
                        status="time_sensitive",
                        reason="Résultat daté à lire dans son contexte",
                    ),
                }
            )

    cover = await pipeline(MemoryStore([item]), Model(plan, [finalize_all])).run(request())
    assert bool(cover.items) is accepted
    if accepted:
        assert cover.items[0].reading_kind == "research"


async def test_temporal_rejection_is_not_screened_again_and_is_visible_to_editor():
    old = article().model_copy(update={"published_at": utcnow() - timedelta(days=90)})

    class Model(ScriptedModel):
        screens = 0

        async def screen(self, state, budget):
            self.screens += 1
            return await super().screen(state, budget)

    model = Model()
    runner = pipeline(MemoryStore([old]), model)
    first = await runner._act(
        decision("search_catalog", query="Python performance"), request(), set()
    )
    second = await runner._act(
        decision("search_catalog", query="systèmes distribués"), request(), set()
    )
    assert first["rejections"][0]["article_id"] == old.id
    assert second["added_ids"] == []
    assert model.screens == 1
    # Full text is evaluated once; the rejection prevents subsequent paid retries.
    assert model.summary_calls == 1


async def test_permuting_an_unsuccessful_query_does_not_spend_another_search():
    runner = pipeline(MemoryStore(), ScriptedModel())
    runner.search_history = [
        {"action": "search_catalog", "query": "musique histoire patrimoine", "added": 0}
    ]
    with pytest.raises(ValueError, match="déjà infructueuse"):
        await runner._act(
            decision("search_catalog", query="patrimoine musique histoire"), request(), set()
        )
    assert runner.budget.counts["search_catalog"] == 0


async def test_invalid_search_without_query_does_not_poison_the_next_valid_search():
    runner = pipeline(MemoryStore(), ScriptedModel())
    runner.search_history = [{"action": "search_web", "query": None, "added": 0}]
    outcome = await runner._act(decision("search_catalog", query="préhistoire"), request(), set())
    assert outcome["added_ids"] == []


async def test_profile_interpretation_does_not_require_quotations():
    model = ScriptedModel()
    model.interpret = AsyncMock(
        return_value=EditorialIntent.model_validate(
            {
                "needs": [
                    {
                        "topic": "Histoire",
                        "query": "histoire",
                        "priority": "primary",
                        "level": "intermediate",
                        "origin": "notes",
                    }
                ],
                "constraints": [{"requirement": "Privilégier les analyses historiques"}],
            }
        )
    )
    cover = await pipeline(MemoryStore(), model).run(
        request(notes="J'aime l'histoire des sciences")
    )
    assert cover.diagnostics["editorial_intent"]["constraints"] == [
        {"requirement": "Privilégier les analyses historiques"}
    ]
    assert cover.diagnostics["editorial_intent"]["needs"][0]["topic"] == "Histoire"
    assert not any(e["kind"] == "intent_items_rejected" for e in cover.diagnostics["events"])


@pytest.mark.parametrize(
    "kind,status,accepted",
    [
        ("evergreen", "durable", True),
        ("news", "time_sensitive", False),
        ("research", "time_sensitive", False),
        ("evergreen", "uncertain", False),
    ],
)
async def test_full_text_can_correct_preview_temporality_without_relaxing_final_rules(
    kind, status, accepted
):
    item = article(title="Une méthode pratique").model_copy(
        update={
            "published_at": utcnow() - timedelta(days=800),
            "text": "Python systèmes distribués : une méthode pratique. " * 20,
            "extraction_status": "extracted",
        }
    )
    plan = plan_for([item])
    plan.picks[0].temporal_kind = "news"

    class Model(PlannedModel):
        async def summarize(self, item, budget):
            brief = await super().summarize(item, budget)
            return brief.model_copy(
                update={
                    "validity": ReadingValidity(
                        kind=kind,
                        status=status,
                        reason="Évaluation du texte intégral",
                    )
                }
            )

    cover = await pipeline(MemoryStore([item]), Model(plan, [finalize_all])).run(request())
    assert bool(cover.items) is accepted
    assert any(e["kind"] == "temporal_review_requested" for e in cover.diagnostics["events"])
    if accepted:
        assert cover.items[0].reading_kind == "evergreen"
        assert cover.items[0].published_at == item.published_at


async def test_specific_notes_stay_primary_when_model_prefers_broad_ui_interests():
    model = ScriptedModel()
    model.interpret = AsyncMock(
        return_value=EditorialIntent.model_validate(
            {
                "needs": [
                    {
                        "topic": "Python",
                        "query": "Python",
                        "priority": "primary",
                        "level": "intermediate",
                        "origin": "profile",
                    },
                    {
                        "topic": "Histoire des sciences",
                        "query": "history science instruments",
                        "priority": "secondary",
                        "level": "expert",
                        "origin": "notes",
                    },
                ],
                "constraints": [],
            }
        )
    )
    runner = pipeline(MemoryStore(), model)
    await runner._interpret(request(notes="Histoire des sciences et instruments"))
    assert [n["priority"] for n in runner.intent["needs"]] == ["secondary", "primary"]
    assert runner.intent["needs"][1]["level"] == "expert"


async def test_constraints_can_use_structured_profile_fields_without_quotations():
    model = ScriptedModel()
    model.interpret = AsyncMock(
        return_value=EditorialIntent.model_validate(
            {
                "needs": [
                    {
                        "topic": "Histoire",
                        "query": "histoire",
                        "priority": "primary",
                        "level": "intermediate",
                        "origin": "notes",
                    }
                ],
                "constraints": [
                    {
                        "requirement": "Lire en français et en anglais",
                    }
                ],
            }
        )
    )
    req = request(notes="Histoire des sciences")
    req.profile.languages = ["fr", "en"]
    runner = pipeline(MemoryStore(), model)
    await runner._interpret(req)
    assert len(runner.intent["constraints"]) == 1
    assert not runner.warnings


async def test_final_selection_accepts_a_brief_without_quotations():
    item = article()
    runner = pipeline(MemoryStore([item]), PlannedModel(plan_for([item]), []))
    await runner.run(request())
    runner.plan.contract_version = 2
    runner.candidates[item.id].brief.validity = ReadingValidity(
        kind="evergreen",
        status="durable",
        reason="Concept durable",
    )
    selection = Selection(
        article_id=item.id,
        section=runner.plan.sections[0],
        reason="Lien documenté",
        headline="Un titre",
        role="lead",
        matched_need="need-1",
        story_key="un sujet",
    )
    assert runner._validate([selection], request()) == []
    assert "evidence" not in selection.model_dump()


async def test_layout_overflow_preserves_articles_and_editor_order_without_fallback():
    items = [
        article(n, title=title)
        for n, title in enumerate(
            [
                "Mécanique quantique",
                "Instruments astronomiques",
                "Géométrie différentielle",
                "Archéologie préhistorique",
                "Manuscrits médiévaux",
                "Musique andine",
                "Écriture littéraire",
            ]
        )
    ]
    runner = pipeline(MemoryStore(items), PlannedModel(plan_for(items), []))
    req = request(size=7)
    req.max_per_source = 7
    await runner.run(req)
    runner.plan.contract_version = 2
    roles = ["lead", "secondary", "secondary", "brief", "brief", "brief", "brief"]
    choices = [
        Selection(
            article_id=a.id,
            section=runner.plan.sections[0],
            reason="Apport",
            headline=a.title,
            role=role,
            matched_need="need-1",
            story_key=a.title,
        )
        for a, role in zip(items, roles, strict=True)
    ]
    kept, removed = runner._allocate(choices, req)
    assert [s.article_id for s in kept] == [a.id for a in items]
    assert not removed
    assert kept[-1].role == "reading"
    assert runner._validate(kept, req) == []


def test_explicit_notes_and_compiled_needs_influence_retrieval_before_llm_plan():
    history = article(1, title="Histoire des sciences : instruments de mesure")
    generic = article(2, title="Python logiciel développement architecture")
    req = request(notes="Histoire des sciences et instruments de mesure")
    rows = rank(
        [history, generic],
        req.profile,
        needs=[
            {"id": "need-1", "query": "histoire sciences instruments mesure", "priority": "primary"}
        ],
    )
    assert rows[0].article.id == history.id
    assert rows[0].score_details["needs"]["need-1"] > 0


async def test_high_score_still_requires_a_known_need_before_summary():
    item = article()
    plan = plan_for([item], [95])
    plan.contract_version = 2
    pick = plan.picks[0]
    pick.matched_need = "unknown"
    pick.temporal_kind = "research"
    model = PlannedModel(plan, [])
    cover = await pipeline(MemoryStore([item]), model).run(request())
    assert not cover.items
    assert model.summary_calls == 0


async def test_partial_editions_also_reject_wrong_sections_and_duplicate_story_without_angle():
    items = [article(1, title="Python annonce alpha"), article(2, title="Autre analyse beta")]
    runner = pipeline(MemoryStore(items), PlannedModel(plan_for(items), []))
    await runner.run(request(size=3))
    runner.plan.contract_version = 2
    selections = [
        Selection(
            article_id=a.id,
            section="Rubrique inventée",
            reason="Lien",
            headline=a.title,
            role="lead" if n == 0 else "secondary",
            matched_need="need-1",
            story_key="même annonce",
        )
        for n, a in enumerate(items)
    ]
    errors = runner._validate(selections, request(size=3))
    assert any("rubriques" in e for e in errors)
    assert any("sans apport distinct" in e for e in errors)


async def test_low_remaining_budget_finalizes_a_partial_edition_instead_of_searching():
    class Model(ScriptedModel):
        async def summarize(self, item, budget):
            result = await super().summarize(item, budget)
            budget.take("screen", 60_000)
            return result

    model = Model([finalize_first])
    cover = await pipeline(
        MemoryStore([article()]), model, max_token_budget=100_000, final_token_reserve=30_000
    ).run(request(size=2))
    assert model.states[0]["force_finalize"] is True
    assert cover.status == "partial"
    assert not cover.usage["calls"].get("search_web")


async def test_adapter_disallows_source_proposal_with_incomplete_cover_and_honors_final_only():
    model = OpenAILanguageModel("test", "test-summary", "test-editor", 1000)
    model._parse = AsyncMock(return_value=decision())
    state = {
        "candidates": [{"article_id": "known"}],
        "size": 18,
        "remaining_steps": 2,
        "discover_sources": True,
        "remaining_source_proposals": 1,
        "coverage": {"source_capacity_upper_bound": 12},
    }
    try:
        await model.decide(state, RunBudget({}, 100_000))
        schema = model._parse.call_args.args[3]
        with pytest.raises(ValidationError):
            schema.model_validate(decision("propose_source").model_dump())
        state.update(force_finalize=True, remaining_web_searches=1, web_search_enabled=True)
        await model.decide(state, RunBudget({}, 100_000))
        schema = model._parse.call_args.args[3]
        with pytest.raises(ValidationError):
            schema.model_validate(decision("search_web", query="autre besoin").model_dump())
    finally:
        await model.close()


async def test_fallback_keeps_original_titles_despite_cached_translation_and_editorial_order():
    first, second = article(1), article(2)
    plan = plan_for([first, second], [71, 95])

    class Model(PlannedModel):
        async def summarize(self, item, budget):
            return (await super().summarize(item, budget)).model_copy(
                update={"headline": "Titre français conservé"}
            )

    cover = await pipeline(MemoryStore([first, second]), Model(plan, [])).run(request(size=2))
    assert cover.status == "fallback"
    assert cover.items[0].article_id == second.id
    assert cover.items[0].role == "lead"
    assert all(i.headline == i.title for i in cover.items)
