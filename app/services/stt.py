import asyncio
import audioop
import io
import os
import tempfile
import wave

import whisper

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        _model = whisper.load_model(settings.whisper_model)
    return _model


async def transcribe_audio(audio_bytes: bytes, language: str | None = None) -> str:
    """Convertit l'audio mulaw 8kHz Twilio en texte via Whisper local. Retry x3."""
    wav_data = _mulaw_to_wav(audio_bytes)
    # whisper_language vide → None → Whisper auto-détecte la langue
    lang: str | None = language or (settings.whisper_language or None)

    last_exc: Exception | None = None
    for attempt in range(settings.max_retries):
        tmp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(wav_data)
                tmp_path = tmp.name

            result = await asyncio.to_thread(
                _get_model().transcribe,
                tmp_path,
                language=lang,
                fp16=False,
            )
            return str(result["text"]).strip()

        except Exception as exc:
            last_exc = exc
            logger.warning("stt_retry", attempt=attempt + 1, error=str(exc))
            await asyncio.sleep(0.4 * (attempt + 1))

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    raise RuntimeError(f"STT échoué après {settings.max_retries} tentatives") from last_exc


def _mulaw_to_wav(mulaw_data: bytes) -> bytes:
    """Convertit mulaw 8kHz en WAV PCM 16kHz pour Whisper."""
    pcm_data = audioop.ulaw2lin(mulaw_data, 2)
    pcm_data = audioop.ratecv(pcm_data, 2, 1, 8000, 16000, None)[0]

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm_data)
    return buf.getvalue()
