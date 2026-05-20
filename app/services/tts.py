"""TTS service — edge-tts par défaut, ElevenLabs si ELEVENLABS_API_KEY configuré.
Streaming par phrase : split le texte en phrases, TTS chaque phrase indépendamment
pour réduire la latence temps-à-premier-audio (first-byte latency).
"""

import asyncio
import re
import subprocess
from collections.abc import AsyncIterator

import edge_tts
import httpx

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+(?=[A-ZÀ-Ûa-zà-û])")


def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases pour le streaming TTS."""
    parts = _SENTENCE_RE.split(text.strip())
    # Fusionne les fragments trop courts (< 8 chars) avec le suivant
    result: list[str] = []
    buf = ""
    for part in parts:
        buf = (buf + " " + part).strip() if buf else part
        if len(buf) >= 8:
            result.append(buf)
            buf = ""
    if buf:
        result.append(buf)
    return result or [text]


async def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Convertit du texte en audio mulaw 8kHz pour Twilio. Retry x3."""
    if settings.elevenlabs_api_key:
        return await _elevenlabs_tts(text)
    return await _edgetts_tts(text, voice)


async def synthesize_streaming(text: str) -> AsyncIterator[bytes]:
    """Génère l'audio phrase par phrase pour réduire la latence first-byte."""
    for sentence in split_sentences(text):
        try:
            yield await synthesize_speech(sentence)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("tts_sentence_error", error=str(exc), sentence=sentence[:40])


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


async def _edgetts_tts(text: str, voice: str | None = None) -> bytes:
    selected_voice = voice or settings.agent_voice
    last_exc: Exception | None = None

    for attempt in range(settings.max_retries):
        try:
            communicate = edge_tts.Communicate(text, selected_voice)
            mp3_chunks: list[bytes] = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    mp3_chunks.append(chunk["data"])
            mp3_data = b"".join(mp3_chunks)
            return await asyncio.to_thread(_mp3_to_mulaw8k, mp3_data)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            last_exc = exc
            logger.warning("tts_retry", attempt=attempt + 1, error=str(exc))
            await asyncio.sleep(0.4 * (attempt + 1))

    raise RuntimeError(f"TTS échoué après {settings.max_retries} tentatives") from last_exc


async def _elevenlabs_tts(text: str) -> bytes:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    last_exc: Exception | None = None

    for attempt in range(settings.max_retries):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    url,
                    headers={"xi-api-key": settings.elevenlabs_api_key},
                    json={
                        "text": text,
                        "model_id": settings.elevenlabs_model_id,
                        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                    },
                )
                resp.raise_for_status()
                return await asyncio.to_thread(_mp3_to_mulaw8k, resp.content)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            last_exc = exc
            logger.warning("elevenlabs_retry", attempt=attempt + 1, error=str(exc))
            await asyncio.sleep(0.4 * (attempt + 1))

    raise RuntimeError(
        f"ElevenLabs TTS échoué après {settings.max_retries} tentatives"
    ) from last_exc


def _mp3_to_mulaw8k(mp3_data: bytes) -> bytes:
    """Convertit MP3 en mulaw 8kHz pour Twilio Media Streams."""
    result = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-ar", "8000", "-ac", "1", "-f", "mulaw", "pipe:1"],
        input=mp3_data,
        capture_output=True,
        check=True,
    )
    return result.stdout
