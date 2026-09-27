import io
import json
import wave
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.dictation import MAX_BYTES, SAMPLE_RATE, GradiumDictation, validate_audio
from tests.auth_fakes import AuthMemoryStore
from tests.test_auth import HEADERS, ORIGIN, register


def wav(seconds=1, rate=SAMPLE_RATE):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * int(rate * seconds))
    return buffer.getvalue()


@pytest.fixture
def dictation():
    store = AuthMemoryStore()
    app = create_app(
        Settings(_env_file=None, openai_api_key=None, gradium_api_key="test-key"), store=store
    )
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
        account = register(client)
        service = SimpleNamespace(
            enabled=True,
            active=set(),
            transcribe=AsyncMock(return_value="Plus d’histoire des sciences."),
        )
        app.state.dictation = service
        yield client, account["id"], service, store


def test_dictation_is_a_private_draft_without_message_or_preference_mutation(dictation):
    client, user_id, service, store = dictation
    path = f"/v1/readers/{user_id}/dictation"
    assert client.get(path).json() == {"enabled": True, "max_seconds": 90}
    audio = wav()
    response = client.post(path, content=audio, headers={"Content-Type": "audio/wav"})
    assert response.status_code == 200
    assert response.json() == {"text": "Plus d’histoire des sciences."}
    assert response.headers["Cache-Control"] == "no-store"
    service.transcribe.assert_awaited_once_with(audio)
    assert not store.preferences and not store.reader_messages and not service.active
    assert "test-key" not in response.text


def test_dictation_requires_owner_session_and_csrf(dictation):
    client, user_id, service, _ = dictation
    path = f"/v1/readers/{user_id}/dictation"
    assert (
        client.post(
            "/v1/readers/someone-else/dictation",
            content=wav(),
            headers={"Content-Type": "audio/wav"},
        ).status_code
        == 403
    )
    assert client.get("/v1/readers/someone-else/dictation").status_code == 403
    client.headers.pop("X-Kiosque-CSRF")
    assert (
        client.post(path, content=wav(), headers={"Content-Type": "audio/wav"}).status_code == 403
    )
    client.cookies.clear()
    assert client.get(path).status_code == 401
    assert (
        client.post(path, content=wav(), headers={"Content-Type": "audio/wav"}).status_code == 401
    )
    service.transcribe.assert_not_awaited()


@pytest.mark.parametrize(
    ("body", "kind", "status"),
    [
        (b"invalid", "audio/wav", 422),
        (wav()[:-2], "audio/wav", 422),
        (wav(0.1), "audio/wav", 422),
        (wav(rate=48000), "audio/wav", 422),
        (b"x" * (MAX_BYTES + 1), "audio/wav", 413),
        (b"invalid", "audio/webm", 415),
    ],
    ids=["invalid", "truncated", "too-short", "wrong-rate", "too-large", "wrong-format"],
)
def test_invalid_recordings_never_reach_provider(dictation, body, kind, status):
    client, user_id, service, _ = dictation
    response = client.post(
        f"/v1/readers/{user_id}/dictation", content=body, headers={"Content-Type": kind}
    )
    assert response.status_code == status
    service.transcribe.assert_not_awaited()
    assert not service.active


def test_unavailable_busy_and_rate_limited_dictation(dictation):
    client, user_id, service, store = dictation
    path = f"/v1/readers/{user_id}/dictation"
    service.enabled = False
    assert client.get(path).json()["enabled"] is False
    assert (
        client.post(path, content=wav(), headers={"Content-Type": "audio/wav"}).status_code == 503
    )
    service.enabled = True
    service.active.add(user_id)
    assert (
        client.post(path, content=wav(), headers={"Content-Type": "audio/wav"}).status_code == 429
    )
    service.active.clear()
    store.auth_attempt = lambda *_: False
    assert (
        client.post(path, content=wav(), headers={"Content-Type": "audio/wav"}).status_code == 429
    )
    service.transcribe.assert_not_awaited()


async def test_gradium_request_and_complete_ndjson_transcription():
    calls = []

    def handle(request):
        calls.append(request)
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["content-type"] == "audio/wav"
        assert json.loads(request.url.params["json_config"]) == {"language": "fr"}
        assert request.content == wav()
        return httpx.Response(
            200,
            text='{"type":"text","text":"Plus de"}\n'
            '{"type":"text","text":"sciences."}\n{"type":"end_text"}\n',
        )

    service = GradiumDictation("test-key", transport=httpx.MockTransport(handle))
    assert await service.transcribe(wav()) == "Plus de sciences."
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (401, "secret provider details", 503),
        (200, '{"type":"error","message":"private details"}', 503),
        (200, '{"type":"text","text":"incomplete"}', 503),
        (200, "invalid JSON", 503),
        (200, '{"type":"end_text"}', 422),
        (200, "x" * 128001, 503),
    ],
    ids=["unauthorized", "provider-error", "incomplete", "invalid-json", "empty", "too-large"],
)
async def test_provider_failures_are_sanitized_and_never_retried(status, body, expected):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text=body)

    service = GradiumDictation("test-key", transport=httpx.MockTransport(handle))
    with pytest.raises(HTTPException) as raised:
        await service.transcribe(wav())
    assert raised.value.status_code == expected
    assert "private" not in raised.value.detail and "test-key" not in raised.value.detail
    assert len(calls) == 1


def test_wav_duration_cannot_be_faked_by_short_payload():
    valid = wav(90)
    validate_audio(valid)
    with pytest.raises(HTTPException):
        validate_audio(valid[:100])
    with pytest.raises(HTTPException):
        validate_audio(wav(91))
