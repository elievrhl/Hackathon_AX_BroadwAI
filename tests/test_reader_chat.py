from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.llm import ModelError, OpenAILanguageModel, RunBudget
from broadwai.models import PreferenceCreate, PreferenceInput, Profile
from broadwai.reader_chat import ReaderChange, ReaderMessage, ReaderReply
from tests.fakes import MemoryStore, ScriptedModel


def message(text="Plus d’histoire des sciences", user="alice"):
    return ReaderMessage(
        id=uuid4().hex,
        message=text,
        profile=Profile(user_id=user, interests=[{"topic": "Sciences"}]),
    )


def reply(*, id_=None, action="more", target="Histoire des sciences", scope="persistent"):
    return ReaderReply(
        reply="Je retiens votre envie pour les prochaines éditions.",
        changes=[
            ReaderChange(
                preference_id=id_,
                preference=PreferenceInput(
                    action=action,
                    target_kind="topic",
                    target=target,
                    scope=scope,
                ),
            ),
        ],
    )


def client_for(store, model):
    return TestClient(
        create_app(
            Settings(_env_file=None, openai_api_key=None, image_review_enabled=False),
            store=store,
            model=model,
        )
    )


def test_chat_create_correct_remove_history_and_idempotency():
    store = MemoryStore()
    model = ScriptedModel()
    model.reader_message = AsyncMock(return_value=reply())
    first = message()
    root = "/v1/readers/alice/messages"
    with client_for(store, model) as client:
        sent = client.post(root, json=first.model_dump(mode="json"))
        assert sent.status_code == 201
        assert sent.json()["changes"][0]["kind"] == "added"
        rule = store.list_preferences("alice", active_only=True)[0]
        assert rule.target == "Histoire des sciences"
        assert client.post(root, json=first.model_dump(mode="json")).json() == sent.json()
        assert model.reader_message.await_count == 1
        changed_body = first.model_copy(update={"message": "Un autre message"})
        assert client.post(root, json=changed_body.model_dump(mode="json")).status_code == 409
        assert client.get("/v1/readers/bob/messages").json() == []
        assert (
            client.post("/v1/readers/bob/messages", json=first.model_dump(mode="json")).status_code
            == 422
        )

        model.reader_message.return_value = reply(id_=rule.id, action="less", scope="next")
        correction = message("Finalement moins, pour la prochaine édition seulement")
        assert client.post(root, json=correction.model_dump(mode="json")).status_code == 201
        current = store.list_preferences("alice", active_only=True)
        assert len(current) == 1 and current[0].action == "less" and current[0].scope == "next"
        state = model.reader_message.call_args.args[0]
        assert state["conversation"][0]["message"] == first.message
        assert state["preferences"][0]["id"] == rule.id

        model.reader_message.return_value = ReaderReply(
            reply="J’oublie cette préférence.",
            changes=[
                ReaderChange(preference_id=rule.id, preference=None),
            ],
        )
        assert (
            client.post(
                root, json=message("Oublie cette préférence").model_dump(mode="json")
            ).status_code
            == 201
        )
        assert not store.list_preferences("alice", active_only=True)
        # Replaying an old message must never resurrect a removed preference.
        assert client.post(root, json=first.model_dump(mode="json")).status_code == 201
        assert not store.list_preferences("alice", active_only=True)
        assert len(client.get(root).json()) == 3


@pytest.mark.parametrize("problem", ["model", "unknown_id", "duplicate_target", "capacity", "race"])
def test_chat_failures_do_not_partially_update_the_fiche(problem):
    store = MemoryStore()
    model = ScriptedModel()
    plan = reply()
    expected = 502
    if problem == "unknown_id":
        plan.changes.append(ReaderChange(preference_id="someone-elses-rule", preference=None))
    if problem == "duplicate_target":
        plan.changes.append(reply(action="exclude").changes[0])
    if problem == "capacity":
        for i in range(12):
            store.create_preference(
                "alice", PreferenceCreate(action="more", target_kind="topic", target=f"Sujet {i}")
            )
    initial = store.list_preferences("alice", active_only=True)

    async def answer(state, budget):
        if problem == "model":
            raise ModelError("Unavailable")
        if problem == "race":
            store.create_preference(
                "alice", PreferenceCreate(action="more", target_kind="topic", target="Autre onglet")
            )
        return plan

    if problem == "race":
        expected = 409
    model.reader_message = answer
    with client_for(store, model) as client:
        response = client.post("/v1/readers/alice/messages", json=message().model_dump(mode="json"))
        assert response.status_code == expected
        assert store.list_reader_messages("alice") == []
        if problem == "race":
            assert [p.target for p in store.list_preferences("alice", active_only=True)] == [
                "Autre onglet"
            ]
        else:
            assert store.list_preferences("alice", active_only=True) == initial


def test_clarification_and_greeting_are_saved_without_changing_preferences():
    store = MemoryStore()
    model = ScriptedModel()
    model.reader_message = AsyncMock(
        return_value=ReaderReply(reply="Quels sujets aimeriez-vous approfondir ?", changes=[])
    )
    with client_for(store, model) as client:
        assert (
            client.post(
                "/v1/readers/alice/messages", json=message("Plus de recul").model_dump(mode="json")
            ).status_code
            == 201
        )
        assert not store.list_preferences("alice")
        for value in [" ", "!!", "a" * 2001]:
            body = message().model_dump(mode="json")
            body["message"] = value
            assert client.post("/v1/readers/alice/messages", json=body).status_code == 422
        assert model.reader_message.await_count == 1


async def test_message_uses_a_single_bounded_structured_model_call():
    model = OpenAILanguageModel("test", "gpt-test", "editor-test", 1000)
    model.client.responses.parse = AsyncMock(
        return_value=SimpleNamespace(
            status="completed",
            output_parsed=reply(),
            usage=None,
        )
    )
    try:
        budget = RunBudget(limits={"reader_chat": 1}, max_tokens=40000)
        response = await model.reader_message({"message": "Plus d’histoire"}, budget)
        assert response.changes[0].preference.action == "more"
        args = model.client.responses.parse.call_args.kwargs
        assert args["text_format"] is ReaderReply
        assert args["max_output_tokens"] == 2500 and args["store"] is False
        assert args["model"] == "gpt-test"
        assert budget.counts["reader_chat"] == 1
    finally:
        await model.close()
