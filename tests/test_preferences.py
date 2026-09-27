from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from tests.client import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.llm import ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import (
    PreferenceAssessments,
    PreferenceCreate,
    PreferenceUpdate,
    ReaderPreference,
)
from broadwai.preferences import PreferencePolicy, validate_preference
from tests.fakes import MemoryStore, ScriptedModel, article, finalize_first
from tests.test_pipeline import pipeline, request


def preference(**kwargs):
    return PreferenceCreate(action="diversify", target_kind="topic", target="Histoire", **kwargs)


def add_rule(store, *, action="diversify", target="Histoire", target_kind="topic", **kwargs):
    return store.create_preference(
        "alice",
        PreferenceCreate(
            action=action,
            target=target,
            target_kind=target_kind,
            **kwargs,
        ),
    )


def test_preference_api_correction_delete_replay_and_isolation():
    store = MemoryStore()
    with TestClient(
        create_app(Settings(_env_file=None), store=store, model=ScriptedModel())
    ) as client:
        root = "/v1/readers/alice/preferences"
        payload = preference().model_dump()
        created = client.post(root, json=payload)
        assert created.status_code == 201
        first = created.json()
        assert len(client.get(root).json()) == 1
        assert client.get("/v1/readers/bob/preferences").json() == []
        corrected = {
            **payload,
            "action": "less",
            "explanation": "Seulement les annonces",
            "revision": 1,
        }
        corrected.pop("id")
        assert (
            client.put(f"/v1/readers/bob/preferences/{first['id']}", json=corrected).status_code
            == 404
        )
        updated = client.put(root + "/" + first["id"], json=corrected)
        assert updated.status_code == 200
        assert updated.json()["explanation"] == "Seulement les annonces"
        assert client.put(root + "/" + first["id"], json=corrected).status_code == 409
        assert client.delete(root + "/" + first["id"] + "?revision=2").status_code == 200
        assert client.post(root, json=payload).json()["status"] == "deleted"
        assert store.list_preferences("alice", active_only=True) == []


def test_new_explicit_instruction_replaces_same_target_and_bounds_active_rules():
    store = MemoryStore()
    first = add_rule(store, action="exclude", target="Histoire")
    latest = add_rule(store, action="more", target="histoire")
    assert store.preferences[first.id].status == "replaced"
    assert store.list_preferences("alice", active_only=True) == [latest]
    for i in range(11):
        add_rule(store, target=f"Sujet {i}")
    with pytest.raises(ValueError, match="12"):
        add_rule(store, target="Un treizième sujet")


@pytest.mark.parametrize(
    "kind,target",
    [("content_type", "promotional"), ("level", "unknown"), ("source", "not a domain")],
)
def test_invalid_structured_target_is_rejected(kind, target):
    with pytest.raises(ValueError):
        validate_preference(PreferenceCreate(action="exclude", target_kind=kind, target=target))


def test_source_normalization_and_qualified_exclusion_is_not_generalized():
    value = validate_preference(
        PreferenceCreate(action="exclude", target_kind="source", target="https://Example.org/path")
    )
    assert value.target == "example.org"
    rule = ReaderPreference(
        **{**value.model_dump(), "explanation": "Seulement les tribunes"}, user_id="alice"
    )
    policy = PreferencePolicy([rule])
    item = article(source="example.org")
    assert policy.match(rule, item) == "uncertain"
    policy.matches[item.id] = {rule.id: "no"}
    assert not policy.blocked(item)


async def test_article_feedback_details_persist_without_inventing_a_preference():
    store = MemoryStore([article()])
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(request())
    app = create_app(Settings(_env_file=None), store=store, model=ScriptedModel())
    with TestClient(app) as client:
        event = dict(
            user_id="alice",
            cover_id=cover.id,
            article_id=cover.items[0].article_id,
            kind="not_interested",
            reason="too_basic",
            comment="Le sujet m'intéresse toujours",
        )
        assert client.post("/v1/feedback", json=event).status_code == 201
        rows = client.get(f"/v1/readers/alice/feedback/{cover.id}").json()
        assert rows[0]["comment"] == event["comment"]
        assert not store.list_preferences("alice")
        assert client.get(f"/v1/readers/bob/feedback/{cover.id}").status_code == 404
        event["preference"] = preference().model_dump()
        saved = client.post("/v1/feedback", json=event).json()
        assert saved["preference"]["target"] == "Histoire"
        assert len(store.list_preferences("alice")) == 1
        assert client.post("/v1/feedback", json=event).status_code == 201
        assert len(store.list_preferences("alice")) == 1


async def test_semantic_exclusion_also_holds_in_fallback_and_for_other_users():
    unwanted = article(1, title="Cryptomonnaies : les nouveaux marchés")
    wanted = article(2, title="Python : interpréteurs et compilation")
    store = MemoryStore([unwanted, wanted])
    add_rule(store, action="exclude", target="Cryptomonnaies")
    cover = await pipeline(store, ScriptedModel()).run(request(size=2))
    assert [item.article_id for item in cover.items] == [wanted.id]
    assert cover.status == "fallback"
    assert cover.diagnostics["preference_impact"][0]["selected_count"] == 0
    bob = request(size=2)
    bob.profile.user_id = "bob"
    other = await pipeline(store, ScriptedModel()).run(bob)
    assert len(other.items) == 2


@pytest.mark.parametrize("failure", ["error", "omitted", "uncertain", "duplicate"])
async def test_hard_semantic_exclusion_never_passes_an_unverified_candidate(failure):
    class BrokenChecks(ScriptedModel):
        async def assess_preferences(self, state, budget):
            if failure == "error":
                raise ModelError("Service indisponible")
            if failure == "omitted":
                return PreferenceAssessments(assessments=[])
            row = {
                "article_id": state["candidates"][0]["article_id"],
                "preference_id": state["preferences"][0]["id"],
                "match": "uncertain" if failure == "uncertain" else "no",
            }
            return PreferenceAssessments(
                assessments=[row, row] if failure == "duplicate" else [row]
            )

    store = MemoryStore([article()])
    rule = add_rule(
        store,
        action="exclude",
        target_kind="treatment",
        target="Articles promotionnels",
        scope="next",
    )
    cover = await pipeline(store, BrokenChecks()).run(request())
    assert not cover.items
    assert store.preferences[rule.id].status == "active"


async def test_source_and_format_exclusions_do_not_need_semantic_calls():
    items = [article(1, source="blocked.example"), article(2)]
    store = MemoryStore(items)
    add_rule(store, action="exclude", target_kind="source", target="blocked.example")
    add_rule(store, action="exclude", target_kind="content_type", target="analysis")
    cover = await pipeline(store, ScriptedModel()).run(request(size=2))
    assert not cover.items
    assert not cover.usage["calls"].get("preferences", 0)


async def test_diversification_keeps_baseline_and_caps_all_new_topics_together():
    titles = [
        "Python : interpréteurs",
        "Python : architectures",
        "Python : outils",
        "Python : typage",
        "Python : réseau",
        "Histoire des instruments",
        "Histoire des empires",
        "Histoire des sciences",
    ]
    store = MemoryStore([article(i, title=title) for i, title in enumerate(titles)])
    add_rule(store)
    cover = await pipeline(store, ScriptedModel()).run(request(size=6))
    assert len(cover.items) == 6
    assert sum("Histoire" in item.title for item in cover.items) == 1
    assert sum("Python" in item.title for item in cover.items) == 5
    assert cover.diagnostics["preference_impact"][0]["selected_count"] == 1


async def test_less_is_bounded_without_becoming_a_ban():
    titles = [
        "Histoire des empires",
        "Histoire des instruments",
        "Python : typage",
        "Python : réseau",
        "Python : optimisation",
        "Python : outils",
        "Python : compilation",
    ]
    store = MemoryStore([article(i, title=title) for i, title in enumerate(titles)])
    add_rule(store, action="less")
    cover = await pipeline(store, ScriptedModel()).run(request(size=6))
    assert len(cover.items) == 6
    assert sum("Histoire" in item.title for item in cover.items) == 1


async def test_more_promotes_matches_and_missing_positive_request_is_visible():
    store = MemoryStore(
        [article(1, title="Python : outils"), article(2, title="Histoire des sciences")]
    )
    add_rule(store, action="more")
    cover = await pipeline(store, ScriptedModel()).run(request(size=1))
    assert "Histoire" in cover.items[0].title
    absent = MemoryStore([article()])
    add_rule(absent)
    cover = await pipeline(absent, ScriptedModel()).run(request())
    assert any("Demande non couverte" in w for w in cover.warnings)


async def test_next_edition_rule_is_consumed_only_on_nonempty_success_and_not_after_a_correction():
    store = MemoryStore([article()])
    rule = add_rule(store, scope="next")
    cover = await pipeline(store, ScriptedModel([finalize_first])).run(request())
    assert store.preferences[rule.id].status == "applied"
    assert store.preferences[rule.id].applied_cover_id == cover.id
    rule = add_rule(store, scope="next")

    class CorrectDuringGeneration(ScriptedModel):
        async def decide(self, state, budget):
            store.update_preference(
                "alice",
                rule.id,
                PreferenceUpdate(
                    **rule.model_dump(
                        include={"action", "target_kind", "target", "explanation", "scope"}
                    ),
                    revision=rule.revision,
                ),
            )
            return finalize_first(state)

    await pipeline(store, CorrectDuringGeneration(), max_agent_steps=1).run(request())
    assert store.preferences[rule.id].status == "active"


async def test_preference_adapter_is_bounded_uses_summary_model_and_accounts_usage():
    model = OpenAILanguageModel("test", "summary-test", "editor-test", 1000)
    result = PreferenceAssessments(assessments=[])
    model.client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output_parsed=result,
            usage=SimpleNamespace(input_tokens=100, output_tokens=10),
        )
    )
    budget = RunBudget(limits={"preferences": 1}, max_tokens=50000)
    try:
        assert (
            await model.assess_preferences({"preferences": [], "candidates": []}, budget) == result
        )
        args = model.client.responses.parse.call_args.kwargs
        assert args["model"] == "summary-test" and args["max_output_tokens"] <= 6000
        assert args["store"] is False
        assert budget.input_tokens == 100
    finally:
        await model.close()
