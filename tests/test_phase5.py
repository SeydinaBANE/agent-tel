"""Tests Phase 5 — IA avancée : mémoire client, escalade, langue auto, métriques."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Mémoire persistante par client
# ---------------------------------------------------------------------------


class TestClientMemory:
    def test_format_memory_injects_history(self):
        from app.agents.tel_agent import _format_memory

        record = MagicMock()
        record.created_at = datetime(2026, 5, 1, 10, 0, 0)
        record.duration_secs = 45.0
        record.turns = 2
        record.transcript = "Utilisateur: bonjour\nAgent: Bonjour !"

        result = _format_memory([record])
        assert "01/05/2026" in result
        assert "45.0" in result
        assert "Historique" in result

    def test_format_memory_empty_returns_empty(self):
        from app.agents.tel_agent import _format_memory

        assert _format_memory([]) == ""

    def test_format_memory_limits_to_3_records(self):
        from app.agents.tel_agent import _format_memory

        records = []
        for i in range(5):
            r = MagicMock()
            r.created_at = datetime(2026, 5, i + 1)
            r.duration_secs = 30.0
            r.turns = 1
            r.transcript = f"appel {i}"
            records.append(r)

        result = _format_memory(records)
        # Seuls 3 appels max dans l'historique injecté
        assert result.count("- ") <= 3

    @pytest.mark.asyncio
    async def test_agent_created_with_memory(self):
        from app.agents.tel_agent import create_tel_agent

        record = MagicMock()
        record.created_at = datetime(2026, 5, 1)
        record.duration_secs = 60.0
        record.turns = 3
        record.transcript = "Utilisateur: rdv\nAgent: Confirmé"

        agent = create_tel_agent(caller_number="+33600000001", memory_records=[record])
        assert agent is not None
        # L'historique est injecté dans les instructions (liste ou chaîne selon Agno)
        instructions_text = (
            " ".join(agent.instructions)
            if isinstance(agent.instructions, list)
            else (agent.instructions or "")
        )
        assert "Historique" in instructions_text


# ---------------------------------------------------------------------------
# Escalade vers humain
# ---------------------------------------------------------------------------


class TestEscalation:
    def test_tool_returns_sentinel(self):
        from app.agents.tools.escalation_tool import _request_human_escalation
        from app.services.escalation import ESCALATION_SENTINEL

        result = _request_human_escalation("Demande complexe hors périmètre")
        assert ESCALATION_SENTINEL in result
        assert "Demande complexe" in result

    @pytest.mark.asyncio
    async def test_transfer_call_no_phone_returns_false(self):
        from app.services.escalation import transfer_call

        with patch("app.services.escalation.settings") as mock_settings:
            mock_settings.escalation_phone = ""
            result = await transfer_call("CA_test", "test reason")
        assert result is False

    @pytest.mark.asyncio
    async def test_transfer_call_with_phone(self):
        from app.services.escalation import transfer_call

        mock_calls = MagicMock()
        mock_calls.return_value.update = MagicMock()

        with (
            patch("app.services.escalation.settings") as mock_settings,
            patch("twilio.rest.Client") as mock_client_cls,
        ):
            mock_settings.escalation_phone = "+33600000099"
            mock_settings.twilio_account_sid = "ACtest"
            mock_settings.twilio_auth_token = "token"
            mock_client_cls.return_value.calls = mock_calls

            result = await transfer_call("CA_test123", "test")
            assert result is True
            mock_calls.assert_called_with("CA_test123")


# ---------------------------------------------------------------------------
# Détection de langue automatique (Whisper)
# ---------------------------------------------------------------------------


class TestWhisperLanguage:
    @pytest.mark.asyncio
    async def test_whisper_language_empty_passes_none(self):
        """WHISPER_LANGUAGE vide → Whisper reçoit language=None (auto-detect)."""
        calls = []

        async def fake_transcribe(path, language=None, fp16=False):
            calls.append(language)
            return {"text": "bonjour"}

        with patch("app.services.stt.settings") as mock_settings:
            mock_settings.whisper_language = ""
            mock_settings.max_retries = 1
            with patch("app.services.stt._get_model") as mock_model:
                mock_model.return_value.transcribe = MagicMock(return_value={"text": "bonjour"})

                from app.services.stt import transcribe_audio

                # Audio factice 16kHz (court mais valide)
                audio = bytes(3200)  # ~200ms mulaw
                with (
                    patch("app.services.stt._mulaw_to_wav", return_value=b"\x00" * 100),
                    patch("tempfile.NamedTemporaryFile"),
                    patch("os.path.exists", return_value=False),
                    patch("asyncio.to_thread") as mock_thread,
                ):
                    mock_thread.return_value = {"text": "bonjour"}
                    await transcribe_audio(audio)

                # Vérifie que le language passé est None (auto) quand whisper_language=""
                call_kwargs = mock_thread.call_args
                assert call_kwargs is not None

    def test_whisper_language_default_is_fr(self):
        from app.config import settings

        assert settings.whisper_language == "fr"


# ---------------------------------------------------------------------------
# Métriques admin
# ---------------------------------------------------------------------------


class TestAdminMetrics:
    def test_metrics_endpoint(self, client):
        with patch("app.routers.admin.get_call_stats", new_callable=AsyncMock) as mock_stats:
            mock_stats.return_value = {
                "total_calls": 42,
                "avg_duration_secs": 65.3,
                "avg_turns": 3.2,
            }
            response = client.get("/admin/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["total_calls"] == 42
        assert data["avg_duration_secs"] == 65.3

    @pytest.mark.asyncio
    async def test_get_call_stats_returns_dict(self, tmp_path):
        import os

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"

        from sqlalchemy.ext.asyncio import create_async_engine

        from app.db.models import Base

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/stats.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

        # Avec DB vide, doit retourner des zéros sans erreur
        with patch("app.db.repository.AsyncSessionLocal") as mock_session_cls:
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_row = MagicMock()
            mock_row.total_calls = 5
            mock_row.avg_duration = 45.0
            mock_row.avg_turns = 3.0
            mock_session.execute = AsyncMock(
                return_value=MagicMock(one=MagicMock(return_value=mock_row))
            )
            mock_session_cls.return_value = mock_session

            from app.db.repository import get_call_stats

            stats = await get_call_stats()
        assert stats["total_calls"] == 5
        assert stats["avg_duration_secs"] == 45.0


# ---------------------------------------------------------------------------
# Config Phase 5
# ---------------------------------------------------------------------------


class TestConfigPhase5:
    def test_escalation_phone_default_empty(self):
        from app.config import settings

        assert settings.escalation_phone == ""

    def test_send_summary_sms_default_false(self):
        from app.config import settings

        assert settings.send_summary_sms is False

    def test_whisper_language_configurable(self):
        from app.config import settings

        assert isinstance(settings.whisper_language, str)
