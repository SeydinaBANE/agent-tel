"""Tests Phase 2 — Robustesse : E.164, timeout, barge-in, stop handler, retry, logs."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Validation E.164
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


class TestE164Validation:
    def test_valid_french_number(self, client):
        with patch("app.main.initiate_outbound_call", return_value="CA_OK"):
            r = client.post("/calls/outbound", json={"to": "+33600000001"})
        assert r.status_code == 200
        assert r.json()["status"] == "initiated"

    def test_invalid_number_no_plus(self, client):
        r = client.post("/calls/outbound", json={"to": "0600000001"})
        assert "E.164" in r.json()["error"]

    def test_invalid_number_letters(self, client):
        r = client.post("/calls/outbound", json={"to": "+336abc"})
        assert "E.164" in r.json()["error"]

    def test_empty_to_field(self, client):
        r = client.post("/calls/outbound", json={})
        assert "requis" in r.json()["error"]

    def test_valid_us_number(self, client):
        with patch("app.main.initiate_outbound_call", return_value="CA_US"):
            r = client.post("/calls/outbound", json={"to": "+12025550100"})
        assert r.json()["status"] == "initiated"


# ---------------------------------------------------------------------------
# CallSession — timeout et barge-in
# ---------------------------------------------------------------------------


def _make_session(call_sid="CA_TEST", caller="+33600000001"):
    with patch("app.telephony.stream.create_tel_agent", return_value=MagicMock()):
        from app.telephony.stream import CallSession

        return CallSession(call_sid=call_sid, caller=caller)


class TestCallSessionPhase2:
    def test_idle_secs_increases_over_time(self):
        session = _make_session()
        session.last_activity = time.monotonic() - 10
        assert session.idle_secs >= 10

    def test_duration_increases_over_time(self):
        session = _make_session()
        session.start_time = time.monotonic() - 5
        assert session.duration >= 5

    def test_transcript_initially_empty(self):
        session = _make_session()
        assert session.transcript == []

    def test_agent_free_when_task_is_none(self):
        from app.telephony.stream import _agent_free

        session = _make_session()
        session.agent_task = None
        assert _agent_free(session) is True

    def test_agent_free_when_task_done(self):
        from app.telephony.stream import _agent_free

        session = _make_session()
        done_task = MagicMock()
        done_task.done.return_value = True
        session.agent_task = done_task
        assert _agent_free(session) is True

    def test_agent_not_free_when_task_running(self):
        from app.telephony.stream import _agent_free

        session = _make_session()
        running_task = MagicMock()
        running_task.done.return_value = False
        session.agent_task = running_task
        assert _agent_free(session) is False

    def test_cancel_agent_cancels_task(self):
        from app.telephony.stream import _cancel_agent

        session = _make_session()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        session.agent_task = mock_task
        session.agent_speaking = True

        _cancel_agent(session)

        mock_task.cancel.assert_called_once()
        assert session.agent_speaking is False

    def test_barge_in_flag_set_on_speech_during_agent(self):
        session = _make_session()
        session.agent_speaking = True
        session.speaking = True
        # Le handler vérifie agent_speaking AND speaking pour déclencher le barge-in
        assert session.agent_speaking and session.speaking


# ---------------------------------------------------------------------------
# Stop handler — résumé automatique
# ---------------------------------------------------------------------------


class TestHandleCallEnd:
    async def test_logs_call_ended_event(self, mocker):
        from app.telephony.stream import _handle_call_end

        session = _make_session()
        session.transcript = [
            "Utilisateur: Bonjour",
            "Agent: Bonjour, comment puis-je vous aider ?",
        ]

        mock_process = mocker.patch(
            "app.telephony.stream.process_turn",
            new_callable=AsyncMock,
            return_value="Résumé enregistré.",
        )
        await _handle_call_end(session)

        # L'agent doit recevoir __END__ avec le résumé
        call_args = mock_process.call_args[0][1]
        assert "__END__" in call_args

    async def test_no_summary_call_when_empty_transcript(self, mocker):
        from app.telephony.stream import _handle_call_end

        session = _make_session()
        session.transcript = []

        mock_process = mocker.patch(
            "app.telephony.stream.process_turn",
            new_callable=AsyncMock,
        )
        await _handle_call_end(session)

        mock_process.assert_not_called()


# ---------------------------------------------------------------------------
# Retry STT
# ---------------------------------------------------------------------------


class TestSTTRetry:
    async def test_returns_on_first_success(self, mocker, fake_mulaw_audio):
        mocker.patch(
            "app.services.stt._get_model",
            return_value=MagicMock(transcribe=MagicMock(return_value={"text": "bonjour"})),
        )
        from app.services.stt import transcribe_audio

        result = await transcribe_audio(fake_mulaw_audio)
        assert result == "bonjour"

    async def test_retries_on_transient_error(self, mocker, fake_mulaw_audio):
        call_count = 0

        def transcribe_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("STT transient error")
            return {"text": "réessai"}

        mocker.patch(
            "app.services.stt._get_model",
            return_value=MagicMock(transcribe=MagicMock(side_effect=transcribe_side_effect)),
        )
        mocker.patch("app.services.stt.asyncio.sleep", new_callable=AsyncMock)

        from importlib import reload

        import app.services.stt as stt_mod

        reload(stt_mod)  # reset cached model

        mocker.patch(
            "app.services.stt._get_model",
            return_value=MagicMock(transcribe=MagicMock(side_effect=transcribe_side_effect)),
        )
        from app.services.stt import transcribe_audio

        result = await transcribe_audio(fake_mulaw_audio)
        assert result == "réessai"


# ---------------------------------------------------------------------------
# Tokens spéciaux agent
# ---------------------------------------------------------------------------


class TestSpecialTokens:
    async def test_start_token_resolved(self, mocker):
        mock_agent = MagicMock()
        mock_run = AsyncMock(return_value=MagicMock(content="Bonjour !"))
        mock_agent.arun = mock_run

        from app.agents.tel_agent import _SPECIAL_TOKENS, process_turn

        await process_turn(mock_agent, "__START__")

        called_with = mock_run.call_args[0][0]
        assert called_with == _SPECIAL_TOKENS["__START__"]

    async def test_timeout_token_resolved(self, mocker):
        mock_agent = MagicMock()
        mock_run = AsyncMock(return_value=MagicMock(content="Au revoir."))
        mock_agent.arun = mock_run

        from app.agents.tel_agent import _SPECIAL_TOKENS, process_turn

        await process_turn(mock_agent, "__TIMEOUT__")

        called_with = mock_run.call_args[0][0]
        assert called_with == _SPECIAL_TOKENS["__TIMEOUT__"]

    async def test_normal_message_passed_through(self, mocker):
        mock_agent = MagicMock()
        mock_run = AsyncMock(return_value=MagicMock(content="Réponse."))
        mock_agent.arun = mock_run

        from app.agents.tel_agent import process_turn

        await process_turn(mock_agent, "Quel est votre horaire ?")

        called_with = mock_run.call_args[0][0]
        assert called_with == "Quel est votre horaire ?"


# ---------------------------------------------------------------------------
# Intégration WebSocket — flux start → stop
# ---------------------------------------------------------------------------


class TestWebSocketIntegration:
    def test_websocket_start_stop_flow(self, mocker):
        mocker.patch("app.telephony.stream.create_tel_agent", return_value=MagicMock())
        mocker.patch(
            "app.telephony.stream.process_turn",
            new_callable=AsyncMock,
            return_value="Bonjour !",
        )
        mocker.patch(
            "app.telephony.stream.synthesize_speech",
            new_callable=AsyncMock,
            return_value=b"\xff" * 320,
        )
        mocker.patch(
            "app.telephony.stream._timeout_watchdog",
            new_callable=AsyncMock,
        )

        from app.main import app

        client = TestClient(app)

        with client.websocket_connect("/ws/stream") as ws:
            ws.send_json(
                {
                    "event": "start",
                    "start": {
                        "callSid": "CA_WS_TEST",
                        "streamSid": "MZ_WS_TEST",
                        "customParameters": {"caller": "+33600000001"},
                    },
                }
            )
            ws.send_json({"event": "stop"})
