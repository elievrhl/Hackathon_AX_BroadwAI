import pytest

from broadwai.config import Settings
from broadwai.llm import ModelError
from broadwai.models import CoverRequest, Feedback, Interest, Profile
from broadwai.network import RetrievalError
from broadwai.pipeline import CoverPipeline
from tests.fakes import (
    FakeCollector,
    FakeSearch,
    MemoryStore,
    ScriptedModel,
    article,
    decision,
    finalize_first,
)


def request(size=1, **profile_kwargs):
    return CoverRequest(
        profile=Profile(user_id="alice", interests=[Interest(topic="Python")], **profile_kwargs),
        size=size,
    )


def pipeline(store, model, search=None, collector=None, **settings):
    return CoverPipeline(
        store,
        collector or FakeCollector(store),
        search or FakeSearch(),
        model,
        Settings(_env_file=None, **settings),
    )


async def test_agent_searches_observes_and_finalizes():
    store = MemoryStore()
    found = article()
    search = FakeSearch([found])
    model = ScriptedModel([decision("search_web", query="Python"), finalize_first])
    cover = await pipeline(store, model, search).run(request())
    assert cover.status == "complete"
    assert [event.action for event in cover.trace] == ["search_web", "finalize"]
    assert model.states[0]["candidates"] == []
    assert model.states[1]["observations"][0]["added_ids"] == [found.id]
    assert cover.items[0].url == found.url
    assert store.get_cover(cover.id) == cover


async def test_invalid_article_id_is_rejected_then_corrected():
    store = MemoryStore([article()])
    invalid = decision(selections=[{"article_id": "invented", "section": "Test", "reason": "Test"}])
    model = ScriptedModel([invalid, finalize_first])
    cover = await pipeline(store, model).run(request())
    assert cover.status == "complete"
    assert "errors" in model.states[1]["observations"][0]
    assert all(item.article_id != "invented" for item in cover.items)


async def test_cache_reused_across_users_and_invalidated_by_content_change():
    original = article()
    store = MemoryStore([original])
    model = ScriptedModel([finalize_first, finalize_first, finalize_first])
    await pipeline(store, model).run(request())
    second_request = request()
    second_request.profile.user_id = "bob"
    cached = await pipeline(store, model).run(second_request)
    assert model.summary_calls == 1
    assert cached.usage["summary_cache_hits"] == 1
    store.put_article(original.model_copy(update={"text": original.text + " Nouveau résultat."}))
    await pipeline(store, model).run(request())
    assert model.summary_calls == 2


async def test_model_version_invalidates_cache():
    store = MemoryStore([article()])
    first = ScriptedModel([finalize_first])
    await pipeline(store, first).run(request())
    second = ScriptedModel([finalize_first])
    second.summary_version = "test-v2"
    await pipeline(store, second).run(request())
    assert second.summary_calls == 1


async def test_repeated_action_is_not_executed_twice_and_fallback_is_explicit():
    store = MemoryStore([article()])
    action = decision("search_web", query="Python avancé")
    model = ScriptedModel([action, action])
    search = FakeSearch()
    cover = await pipeline(store, model, search, max_agent_steps=2).run(request(size=2))
    assert search.queries == ["Python avancé"]
    assert cover.status == "fallback"
    assert len(cover.items) == 1
    assert "déjà tentée" in cover.trace[1].outcome["error"]


async def test_fetch_failure_retains_excerpt_and_marks_provenance():
    item = article(extracted=False)
    store = MemoryStore([item])

    class BrokenCollector:
        async def extract(self, article):
            raise RetrievalError("Site inaccessible")

    cover = await pipeline(store, ScriptedModel([finalize_first]), collector=BrokenCollector()).run(
        request()
    )
    assert cover.items[0].extraction_status == "excerpt"
    assert any("extrait" in c for c in cover.items[0].brief.caveats)
    assert any("inaccessible" in w for w in cover.warnings)


async def test_title_alone_never_produces_a_summary():
    item = article(extracted=False).model_copy(update={"excerpt": ""})
    store = MemoryStore([item])
    model = ScriptedModel()
    cover = await pipeline(store, model, max_fetches=0).run(request())
    assert cover.items == []
    assert model.summary_calls == 0


async def test_seen_and_excluded_content_cannot_reenter_through_web_search():
    item = article()
    store = MemoryStore()
    model = ScriptedModel([decision("search_web", query="Python")])
    cover = await pipeline(store, model, FakeSearch([item])).run(
        request(seen_article_ids=[item.id]),
    )
    assert cover.items == []
    assert model.summary_calls == 0


async def test_new_full_text_can_disqualify_an_article():
    item = article(extracted=False)
    store = MemoryStore([item])

    class ExcludedCollector:
        async def extract(self, article):
            return store.put_article(
                article.model_copy(
                    update={
                        "text": "cryptomonnaies " * 30,
                        "extraction_status": "extracted",
                    }
                )
            )

    cover = await pipeline(store, ScriptedModel(), collector=ExcludedCollector()).run(
        request(excluded_topics=["cryptomonnaies"]),
    )
    assert not cover.items


async def test_read_article_only_sends_full_text_after_agent_requests_it():
    item = article()
    store = MemoryStore([item])
    model = ScriptedModel([decision("read_article", article_id=item.id), finalize_first])
    cover = await pipeline(store, model).run(request())
    assert "text" not in model.states[0]["candidates"][0]
    assert model.states[1]["observations"][0]["text"] == item.text
    assert "text" not in cover.trace[0].outcome


async def test_summary_failure_is_not_cached_or_fabricated():
    store = MemoryStore([article()])

    class BrokenModel(ScriptedModel):
        async def summarize(self, article, budget):
            raise ModelError("Indisponible")

    cover = await pipeline(store, BrokenModel()).run(request())
    assert not cover.items
    assert not store.briefs


async def test_feedback_excludes_consumed_article_on_next_cover():
    item = article()
    store = MemoryStore([item])
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(request())
    store.add_feedback(
        Feedback(user_id="alice", cover_id=cover.id, article_id=item.id, kind="useful")
    )
    next_cover = await pipeline(store, ScriptedModel()).run(request())
    assert not next_cover.items


@pytest.mark.parametrize("bad_selection", ["duplicate", "source_quota", "too_many"])
async def test_final_selection_constraints(bad_selection):
    items = [
        article(1, title="Python architecture distribuée", source="same.example"),
        article(2, title="Python apprendre les générateurs", source="same.example"),
    ]
    store = MemoryStore(items)
    selected = [items[0], items[0]] if bad_selection == "duplicate" else items
    invalid = decision(
        selections=[
            {"article_id": a.id, "section": "Technique", "reason": "Pertinent"} for a in selected
        ]
    )
    req = request(size=1 if bad_selection == "too_many" else 2)
    req.max_per_source = 1
    cover = await pipeline(store, ScriptedModel([invalid]), max_agent_steps=1).run(req)
    assert cover.status == ("complete" if bad_selection == "too_many" else "partial")
    assert cover.trace[0].outcome["removed_by_constraints"]
    assert cover.items[0].article_id == items[0].id
    assert len(cover.items) <= 1
