"""Tests de la logique CallSession (buffer audio + détection silence)."""
import base64
from unittest.mock import MagicMock, patch

import pytest

from app.telephony.stream import CHUNK_DURATION, SILENCE_THRESHOLD, CallSession


def _make_session() -> CallSession:
    with patch("app.telephony.stream.create_tel_agent", return_value=MagicMock()):
        return CallSession(call_sid="CA_TEST", caller="+33600000001")


class TestCallSession:
    def test_initial_state(self):
        session = _make_session()

        assert len(session.audio_buffer) == 0
        assert session.speaking is False
        assert session.silence_counter == 0

    def test_add_speech_sets_speaking(self):
        session = _make_session()
        # bytes à 0x00 → énergie = 128 >> 5, bcp > seuil 5
        speech_chunk = bytes([0x00] * 160)

        session.add_audio(base64.b64encode(speech_chunk).decode())

        assert session.speaking is True

    def test_add_silence_after_speech_increments_counter(self):
        session = _make_session()
        session.speaking = True
        # 0x80 = 128 → énergie = 0
        silence_chunk = bytes([0x80] * 160)

        session.add_audio(base64.b64encode(silence_chunk).decode())

        assert session.silence_counter == 1

    def test_should_not_transcribe_when_silent_from_start(self):
        session = _make_session()

        assert session.should_transcribe() is False

    def test_should_transcribe_after_silence_threshold(self):
        session = _make_session()
        session.speaking = True
        session.silence_counter = int(SILENCE_THRESHOLD / CHUNK_DURATION) + 1

        assert session.should_transcribe() is True

    def test_flush_returns_buffer_and_resets_state(self):
        session = _make_session()
        session.audio_buffer.extend(b"\x00" * 100)
        session.speaking = True
        session.silence_counter = 5

        data = session.flush_audio()

        assert len(data) == 100
        assert len(session.audio_buffer) == 0
        assert session.speaking is False
        assert session.silence_counter == 0

    def test_audio_accumulates_in_buffer(self):
        session = _make_session()
        chunk = bytes([0x80] * 160)

        session.add_audio(base64.b64encode(chunk).decode())
        session.add_audio(base64.b64encode(chunk).decode())

        assert len(session.audio_buffer) == 320
