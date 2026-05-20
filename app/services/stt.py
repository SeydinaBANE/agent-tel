import asyncio
import io
import os
import tempfile
import wave

import audioop
import whisper

from app.config import settings

_model: whisper.Whisper | None = None


def _get_model() -> whisper.Whisper:
    global _model
    if _model is None:
        _model = whisper.load_model(settings.whisper_model)
    return _model


async def transcribe_audio(audio_bytes: bytes, language: str | None = None) -> str:
    """Convertit l'audio mulaw 8kHz Twilio en texte via Whisper local."""
    wav_data = _mulaw_to_wav(audio_bytes)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(wav_data)
        tmp_path = tmp.name

    try:
        lang = language or settings.agent_language
        result = await asyncio.to_thread(
            _get_model().transcribe,
            tmp_path,
            language=lang,
            fp16=False,
        )
        return str(result["text"]).strip()
    finally:
        os.unlink(tmp_path)


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
