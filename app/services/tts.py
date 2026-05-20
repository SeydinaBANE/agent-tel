import audioop
import io

import edge_tts

from app.config import settings


async def synthesize_speech(text: str, voice: str | None = None) -> bytes:
    """Convertit du texte en audio mulaw 8kHz pour Twilio via edge-tts."""
    selected_voice = voice or settings.agent_voice
    communicate = edge_tts.Communicate(text, selected_voice)

    mp3_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_chunks.append(chunk["data"])

    mp3_data = b"".join(mp3_chunks)
    return _mp3_to_mulaw8k(mp3_data)


def _mp3_to_mulaw8k(mp3_data: bytes) -> bytes:
    """Convertit MP3 (edge-tts) en mulaw 8kHz pour Twilio Media Streams."""
    import subprocess

    result = subprocess.run(
        [
            "ffmpeg", "-i", "pipe:0",
            "-ar", "8000",
            "-ac", "1",
            "-f", "mulaw",
            "pipe:1",
        ],
        input=mp3_data,
        capture_output=True,
        check=True,
    )
    return result.stdout
