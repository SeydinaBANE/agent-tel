import asyncio
import subprocess

import edge_tts

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


async def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Convertit du texte en audio mulaw 8kHz pour Twilio. Retry x3."""
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
            # Conversion ffmpeg dans un thread pour ne pas bloquer l'event loop
            return await asyncio.to_thread(_mp3_to_mulaw8k, mp3_data)

        except asyncio.CancelledError:
            raise  # barge-in — ne pas retenter

        except Exception as exc:
            last_exc = exc
            logger.warning("tts_retry", attempt=attempt + 1, error=str(exc))
            await asyncio.sleep(0.4 * (attempt + 1))

    raise RuntimeError(f"TTS échoué après {settings.max_retries} tentatives") from last_exc


def _mp3_to_mulaw8k(mp3_data: bytes) -> bytes:
    """Convertit MP3 (edge-tts) en mulaw 8kHz pour Twilio Media Streams."""
    result = subprocess.run(
        ["ffmpeg", "-i", "pipe:0", "-ar", "8000", "-ac", "1", "-f", "mulaw", "pipe:1"],
        input=mp3_data,
        capture_output=True,
        check=True,
    )
    return result.stdout
