"""Short, authenticated voice drafts. Audio is processed in memory, never persisted."""

import asyncio
import io
import json
import wave

import httpx
from fastapi import APIRouter, HTTPException, Request

from broadwai.auth import digest

router = APIRouter(prefix="/v1/readers/{user_id}/dictation", tags=["Dictation"])
MAX_SECONDS = 90
SAMPLE_RATE = 24_000
MAX_BYTES = MAX_SECONDS * SAMPLE_RATE * 2 + 4096


def validate_audio(audio: bytes) -> None:
    try:
        with wave.open(io.BytesIO(audio), "rb") as recording:
            frames = recording.getnframes()
            if (
                recording.getnchannels() != 1
                or recording.getsampwidth() != 2
                or recording.getframerate() != SAMPLE_RATE
                or not SAMPLE_RATE // 4 <= frames <= SAMPLE_RATE * MAX_SECONDS
                or len(recording.readframes(frames)) != frames * 2
            ):
                raise ValueError
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(
            422, "L’enregistrement est invalide ou dépasse 90 secondes. Réessayez la dictée."
        ) from None


class GradiumDictation:
    def __init__(self, api_key=None, *, transport=None):
        self.api_key = api_key
        self.transport = transport
        self.active = set()

    @property
    def enabled(self):
        return bool(self.api_key)

    async def transcribe(self, audio: bytes) -> str:
        # No retries: a lost response may already have consumed provider credits.
        try:
            async with (
                asyncio.timeout(45),
                httpx.AsyncClient(
                    timeout=httpx.Timeout(30, connect=8), transport=self.transport, trust_env=False
                ) as client,
            ):
                async with client.stream(
                    "POST",
                    "https://api.gradium.ai/api/post/speech/asr",
                    params={"json_config": json.dumps({"language": "fr"})},
                    headers={"x-api-key": self.api_key, "Content-Type": "audio/wav"},
                    content=audio,
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 128_000:
                            raise ValueError("Oversized transcription")
            parts, complete = [], False
            for line in body.decode("utf-8").splitlines():
                if not line.strip():
                    continue
                message = json.loads(line)
                if not isinstance(message, dict) or message.get("type") == "error":
                    raise ValueError("Transcription unavailable")
                if message.get("type") == "text":
                    if not isinstance(message.get("text"), str):
                        raise ValueError("Invalid transcription")
                    parts.append(message["text"])
                elif message.get("type") == "end_text":
                    complete = True
            if not complete:
                raise ValueError("Incomplete transcription")
            text = " ".join(" ".join(parts).split())
            if len(text) > 12_000:
                raise ValueError("Oversized transcript")
        except (httpx.HTTPError, TimeoutError, ValueError):
            # Never expose provider responses, credentials or audio in diagnostics.
            raise HTTPException(
                503, "La dictée est momentanément indisponible. Votre message écrit est conservé."
            ) from None
        if not text:
            raise HTTPException(422, "Aucune parole reconnue. Réessayez en parlant près du micro.")
        return text


@router.get("")
def availability(user_id: str, request: Request):
    return {"enabled": request.app.state.dictation.enabled, "max_seconds": MAX_SECONDS}


@router.post("")
async def transcribe(user_id: str, request: Request):
    service = request.app.state.dictation
    if not service.enabled:
        raise HTTPException(503, "La dictée est momentanément indisponible.")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "audio/wav":
        raise HTTPException(415, "Format de dictée non pris en charge.")
    account_id = request.state.account["id"]
    if account_id in service.active or len(service.active) >= 4:
        raise HTTPException(429, "Une dictée est déjà en cours. Patientez quelques instants.")
    service.active.add(account_id)
    try:
        audio = bytearray()
        try:
            async with asyncio.timeout(15):
                async for chunk in request.stream():
                    audio.extend(chunk)
                    if len(audio) > MAX_BYTES:
                        raise HTTPException(413, "La dictée est limitée à 90 secondes.")
        except TimeoutError:
            raise HTTPException(408, "L’envoi de la dictée a pris trop de temps.") from None
        validate_audio(audio)
        allowed = await asyncio.to_thread(
            request.app.state.store.auth_attempt, digest("dictation:" + account_id), 20, 900
        )
        if not allowed:
            raise HTTPException(429, "Trop de dictées. Réessayez dans quelques minutes.")
        text = await service.transcribe(bytes(audio))
        return {"text": text}
    finally:
        service.active.discard(account_id)
