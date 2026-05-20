"""Tests Phase 5b — Streaming TTS, ElevenLabs, multi-agents, Railway."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# split_sentences — utilitaire TTS streaming
# ---------------------------------------------------------------------------


class TestSplitSentences:
    def test_splits_on_period(self):
        from app.services.tts import split_sentences

        result = split_sentences("Bonjour. Comment puis-je vous aider ?")
        assert len(result) == 2
        assert result[0] == "Bonjour."

    def test_splits_on_question_mark(self):
        from app.services.tts import split_sentences

        result = split_sentences("Votre rdv est confirmé ! Souhaitez-vous un SMS ?")
        assert len(result) == 2

    def test_short_fragment_merged(self):
        from app.services.tts import split_sentences

        # "Ok." is too short, should be merged with next sentence
        result = split_sentences("Ok. Je vérifie le calendrier pour vous.")
        assert len(result) == 1 or all(len(s) >= 4 for s in result)

    def test_single_sentence_unchanged(self):
        from app.services.tts import split_sentences

        text = "Bonjour je suis votre assistant"
        result = split_sentences(text)
        assert result == [text]

    def test_empty_returns_original(self):
        from app.services.tts import split_sentences

        result = split_sentences("")
        assert result == [""]


# ---------------------------------------------------------------------------
# synthesize_streaming — génère audio par phrase
# ---------------------------------------------------------------------------


class TestSynthesizeStreaming:
    @pytest.mark.asyncio
    async def test_yields_one_chunk_per_sentence(self):
        from app.services.tts import synthesize_streaming

        with patch("app.services.tts.synthesize_speech", new_callable=AsyncMock) as mock_tts:
            mock_tts.return_value = b"\x00" * 100

            chunks = []
            async for chunk in synthesize_streaming("Bonjour. Au revoir."):
                chunks.append(chunk)

        assert len(chunks) == 2
        assert mock_tts.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_failed_sentence(self):
        from app.services.tts import synthesize_streaming

        call_count = 0

        async def _tts_sometimes_fails(text, voice=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("TTS error")
            return b"\x00" * 100

        with patch("app.services.tts.synthesize_speech", side_effect=_tts_sometimes_fails):
            chunks = []
            async for chunk in synthesize_streaming("Bonjour. Au revoir."):
                chunks.append(chunk)

        # La première phrase a échoué (loggée), la deuxième est passée
        assert len(chunks) == 1


# ---------------------------------------------------------------------------
# ElevenLabs TTS backend
# ---------------------------------------------------------------------------


class TestElevenLabsTTS:
    @pytest.mark.asyncio
    async def test_uses_elevenlabs_when_api_key_set(self):
        from app.services.tts import synthesize_speech

        with patch("app.services.tts.settings") as mock_settings:
            mock_settings.elevenlabs_api_key = "el_test_key"
            mock_settings.elevenlabs_voice_id = "voice123"
            mock_settings.elevenlabs_model_id = "eleven_multilingual_v2"
            mock_settings.max_retries = 1

            with patch("app.services.tts._elevenlabs_tts", new_callable=AsyncMock) as mock_el:
                mock_el.return_value = b"\x00" * 100
                result = await synthesize_speech("Bonjour")

        mock_el.assert_called_once_with("Bonjour")
        assert result == b"\x00" * 100

    @pytest.mark.asyncio
    async def test_falls_back_to_edgetts_without_key(self):
        from app.services.tts import synthesize_speech

        with patch("app.services.tts.settings") as mock_settings:
            mock_settings.elevenlabs_api_key = ""
            mock_settings.agent_voice = "fr-FR-DeniseNeural"
            mock_settings.max_retries = 1

            with patch("app.services.tts._edgetts_tts", new_callable=AsyncMock) as mock_edge:
                mock_edge.return_value = b"\x00" * 100
                result = await synthesize_speech("Bonjour")

        mock_edge.assert_called_once()
        assert result == b"\x00" * 100

    @pytest.mark.asyncio
    async def test_elevenlabs_calls_api(self):
        from app.services.tts import _elevenlabs_tts

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.content = b"MP3_FAKE_DATA"

        with (
            patch("app.services.tts.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
            patch("app.services.tts._mp3_to_mulaw8k", return_value=b"\x00" * 50),
            patch("asyncio.to_thread", new_callable=AsyncMock) as mock_thread,
        ):
            mock_settings.elevenlabs_api_key = "el_key"
            mock_settings.elevenlabs_voice_id = "voice123"
            mock_settings.elevenlabs_model_id = "eleven_multilingual_v2"
            mock_settings.max_retries = 1

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_ctx
            mock_thread.return_value = b"\x00" * 50

            result = await _elevenlabs_tts("Bonjour")

        mock_ctx.post.assert_called_once()
        assert result == b"\x00" * 50


# ---------------------------------------------------------------------------
# Multi-agents — architecture superviseur
# ---------------------------------------------------------------------------


class TestMultiAgentTeam:
    def test_create_team_agent_returns_agent(self):
        from agno.agent import Agent

        from app.agents.team import create_team_agent

        agent = create_team_agent(caller_number="+33600000001")
        assert isinstance(agent, Agent)
        assert agent.name == "Superviseur"

    def test_team_agent_has_delegation_tools(self):
        from app.agents.team import create_team_agent

        agent = create_team_agent()
        tool_names = [t.name for t in agent.tools] if agent.tools else []
        assert any("calendar" in name.lower() for name in tool_names)
        assert any("crm" in name.lower() for name in tool_names)

    def test_team_agent_with_memory(self):
        from datetime import datetime
        from unittest.mock import MagicMock

        from app.agents.team import create_team_agent

        record = MagicMock()
        record.created_at = datetime(2026, 5, 1)
        record.duration_secs = 45.0
        record.turns = 2
        record.transcript = "Utilisateur: rdv"

        agent = create_team_agent(caller_number="+33600000001", memory_records=[record])
        assert agent is not None
        instructions_text = (
            " ".join(agent.instructions)
            if isinstance(agent.instructions, list)
            else (agent.instructions or "")
        )
        assert "Historique" in instructions_text


# ---------------------------------------------------------------------------
# Config Phase 5b
# ---------------------------------------------------------------------------


class TestConfigPhase5b:
    def test_tts_sentence_streaming_default_true(self):
        from app.config import settings

        assert settings.tts_sentence_streaming is True

    def test_multi_agent_mode_default_false(self):
        from app.config import settings

        assert settings.multi_agent_mode is False

    def test_elevenlabs_defaults(self):
        from app.config import settings

        assert settings.elevenlabs_api_key == ""
        assert "eleven_multilingual" in settings.elevenlabs_model_id
