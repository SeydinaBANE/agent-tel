"""Tests streaming LLM → TTS : process_turn_streaming + pipeline stream.py."""

from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# process_turn_streaming — tokens spéciaux passent sans streamer
# ---------------------------------------------------------------------------


class TestProcessTurnStreaming:
    @pytest.mark.asyncio
    async def test_special_token_yields_single_text(self):
        from app.agents.tel_agent import process_turn_streaming

        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Bonjour, comment puis-je vous aider ?"
        mock_agent.arun = AsyncMock(return_value=mock_response)

        results = []
        async for kind, content in process_turn_streaming(mock_agent, "__START__"):
            results.append((kind, content))

        assert len(results) == 1
        assert results[0][0] == "text"
        assert "Bonjour" in results[0][1]

    @pytest.mark.asyncio
    async def test_streams_sentences_from_tokens(self):
        """Simule un flux de tokens LLM et vérifie que les phrases sont reconstituées."""
        from agno.utils.events import RunCompletedEvent

        from app.agents.tel_agent import process_turn_streaming

        # Crée des événements qui simulent une réponse en streaming
        events = [
            _make_content_event("Votre rendez-vous"),
            _make_content_event(" est confirmé. "),
            _make_content_event("À demain !"),
            RunCompletedEvent(),
        ]

        mock_agent = MagicMock()
        mock_agent.arun = MagicMock(return_value=_async_iter(events))

        results = []
        async for kind, content in process_turn_streaming(mock_agent, "Merci"):
            results.append((kind, content))

        text_results = [c for k, c in results if k == "text"]
        # Les deux phrases doivent apparaître
        assert any("confirmé" in s for s in text_results)

    @pytest.mark.asyncio
    async def test_detects_escalation_tool_call(self):
        from agno.utils.events import RunCompletedEvent, ToolExecution

        from app.agents.tel_agent import process_turn_streaming
        from app.services.escalation import ESCALATION_SENTINEL

        tool_exec = ToolExecution(
            tool_name="request_human_escalation",
            result=f"{ESCALATION_SENTINEL}: problème complexe",
        )
        events = [
            _make_tool_event(tool_exec),
            RunCompletedEvent(),
        ]

        mock_agent = MagicMock()
        mock_agent.arun = MagicMock(return_value=_async_iter(events))

        results = []
        async for kind, content in process_turn_streaming(mock_agent, "Aide"):
            results.append((kind, content))

        escalade_results = [(k, c) for k, c in results if k == "escalade"]
        assert len(escalade_results) == 1
        assert ESCALATION_SENTINEL in escalade_results[0][1]

    @pytest.mark.asyncio
    async def test_remaining_buffer_yielded_on_completion(self):
        """Les tokens sans frontière de phrase à la fin sont quand même yielded."""
        from agno.utils.events import RunCompletedEvent

        from app.agents.tel_agent import process_turn_streaming

        events = [
            _make_content_event("Bonjour"),
            RunCompletedEvent(),
        ]

        mock_agent = MagicMock()
        mock_agent.arun = MagicMock(return_value=_async_iter(events))

        results = []
        async for kind, content in process_turn_streaming(mock_agent, "Test"):
            results.append((kind, content))

        text_results = [c for k, c in results if k == "text"]
        assert "Bonjour" in " ".join(text_results)


# ---------------------------------------------------------------------------
# Config LLM streaming
# ---------------------------------------------------------------------------


class TestConfigLlmStreaming:
    def test_llm_streaming_default_false(self):
        from app.config import settings

        assert settings.llm_streaming is False

    def test_sentence_boundary_regex(self):
        from app.agents.tel_agent import _SENTENCE_BOUNDARY

        text = "Bonjour. Je suis disponible. À demain !"
        parts = _SENTENCE_BOUNDARY.split(text)
        assert len(parts) == 3


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_content_event(text: str):
    from agno.utils.events import RunContentEvent

    evt = RunContentEvent()
    evt.content = text
    return evt


def _make_tool_event(tool_exec):
    from agno.utils.events import ToolCallCompletedEvent

    evt = ToolCallCompletedEvent()
    evt.tool = tool_exec
    return evt


async def _async_iter_gen(items):
    for item in items:
        yield item


def _async_iter(items):
    return _async_iter_gen(items)
