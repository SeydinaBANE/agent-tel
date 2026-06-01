"""Tests de la chaîne de conversion audio (mulaw ↔ PCM ↔ WAV)."""

import io
import wave


class TestMulawToWav:
    def test_output_is_valid_wav(self, fake_mulaw_audio):
        from app.services.stt import _mulaw_to_wav

        wav_data = _mulaw_to_wav(fake_mulaw_audio)

        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wav:
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getframerate() == 16000

    def test_output_is_non_empty(self, fake_mulaw_audio):
        from app.services.stt import _mulaw_to_wav

        wav_data = _mulaw_to_wav(fake_mulaw_audio)

        assert len(wav_data) > 44  # 44 bytes = header WAV minimum

    def test_resampling_doubles_samples(self, fake_mulaw_audio):
        """Le rééchantillonnage 8kHz→16kHz doit doubler approximativement le nombre d'échantillons."""
        from app.services.stt import _mulaw_to_wav

        wav_data = _mulaw_to_wav(fake_mulaw_audio)

        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wav:
            frames = wav.getnframes()

        input_samples = len(fake_mulaw_audio)
        assert frames > input_samples  # doit être ~2x plus grand


class TestTranscribeAudio:
    async def test_transcribe_returns_string(self, fake_mulaw_audio, mocker):
        mocker.patch(
            "app.services.stt._get_model",
            return_value=mocker.MagicMock(
                transcribe=mocker.MagicMock(return_value={"text": "  bonjour  "})
            ),
        )

        from app.services.stt import transcribe_audio

        result = await transcribe_audio(fake_mulaw_audio)

        assert result == "bonjour"

    async def test_transcribe_handles_empty_result(self, fake_mulaw_audio, mocker):
        mocker.patch(
            "app.services.stt._get_model",
            return_value=mocker.MagicMock(
                transcribe=mocker.MagicMock(return_value={"text": "   "})
            ),
        )

        from app.services.stt import transcribe_audio

        result = await transcribe_audio(fake_mulaw_audio)

        assert result == ""
