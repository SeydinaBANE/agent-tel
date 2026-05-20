"""Tests Phase 3 — Intégrations : DB, CRM, Calendar, Webhook, Admin API."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# CRM service (mock mode — CRM_API_URL vide)
# ---------------------------------------------------------------------------


class TestCRMService:
    @pytest.mark.asyncio
    async def test_get_contact_mock_found(self):
        from app.services.crm import get_contact

        contact = await get_contact("+33600000001")
        assert contact is not None
        assert contact["name"] == "Alice Martin"

    @pytest.mark.asyncio
    async def test_get_contact_mock_not_found(self):
        from app.services.crm import get_contact

        contact = await get_contact("+33699999999")
        assert contact is None

    @pytest.mark.asyncio
    async def test_log_activity_mock(self):
        from app.services.crm import log_activity

        result = await log_activity("+33600000001", "Test appel")
        assert "[mock]" in result
        assert "+33600000001" in result


# ---------------------------------------------------------------------------
# CRM tool
# ---------------------------------------------------------------------------


class TestCRMTool:
    @pytest.mark.asyncio
    async def test_get_client_info_found(self):
        from app.agents.tools.crm_tool import _get_client_info

        result = await _get_client_info("+33600000001")
        assert "Alice Martin" in result
        assert "PRO" in result

    @pytest.mark.asyncio
    async def test_get_client_info_not_found(self):
        from app.agents.tools.crm_tool import _get_client_info

        result = await _get_client_info("+33699999999")
        assert "Aucun client" in result

    @pytest.mark.asyncio
    async def test_log_call_summary(self):
        from app.agents.tools.crm_tool import _log_call_summary

        result = await _log_call_summary("+33600000001", "Demande de renseignements")
        assert result is not None


# ---------------------------------------------------------------------------
# Calendar service (mock mode — GOOGLE_CALENDAR_CREDENTIALS vide)
# ---------------------------------------------------------------------------


class TestCalendarService:
    @pytest.mark.asyncio
    async def test_list_free_slots_mock(self):
        from app.services.calendar_service import list_free_slots

        slots = await list_free_slots("2026-06-01")
        assert isinstance(slots, list)
        assert len(slots) > 0

    @pytest.mark.asyncio
    async def test_create_event_mock(self):
        from app.services.calendar_service import create_event

        event_id = await create_event("2026-06-01", "10:30", "Réunion test")
        assert event_id.startswith("mock_")


# ---------------------------------------------------------------------------
# Calendar tool
# ---------------------------------------------------------------------------


class TestCalendarTool:
    @pytest.mark.asyncio
    async def test_check_availability(self):
        from app.agents.tools.calendar_tool import _check_availability

        result = await _check_availability("2026-06-01")
        assert "Créneaux disponibles" in result
        assert "2026-06-01" in result

    @pytest.mark.asyncio
    async def test_book_appointment(self):
        from app.agents.tools.calendar_tool import _book_appointment

        result = await _book_appointment("2026-06-01", "10:30", "Alice Martin", "Consultation")
        assert "Alice Martin" in result
        assert "confirmé" in result


# ---------------------------------------------------------------------------
# Webhook Slack (mode silencieux si SLACK_WEBHOOK_URL vide)
# ---------------------------------------------------------------------------


class TestWebhook:
    @pytest.mark.asyncio
    async def test_notify_no_url_is_silent(self):
        from app.services.webhook import notify_call_ended

        # Ne lève pas d'exception si SLACK_WEBHOOK_URL est vide
        await notify_call_ended("CA_test", "+33600000001", 42.0, ["Utilisateur: bonjour"])

    @pytest.mark.asyncio
    async def test_notify_posts_to_slack(self):
        from app.services.webhook import notify_call_ended

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("app.services.webhook.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.slack_webhook_url = "https://hooks.slack.com/test"
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_ctx)
            mock_ctx.__aexit__ = AsyncMock(return_value=False)
            mock_ctx.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_ctx

            await notify_call_ended("CA_test", "+33600000001", 42.0, ["Utilisateur: bonjour"])
            mock_ctx.post.assert_called_once()


# ---------------------------------------------------------------------------
# Repository DB (SQLite in-memory)
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session(tmp_path):
    """Base SQLite temporaire pour les tests."""
    import os

    os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"
    # Réimporter pour prendre en compte la nouvelle URL
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.db.models as models_mod

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(models_mod.Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    return Session


class TestRepository:
    @pytest.mark.asyncio
    async def test_save_and_retrieve_call(self, tmp_path):
        import os

        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path}/test.db"

        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.db.models import Base, CallRecord

        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/test.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        Session = async_sessionmaker(engine, expire_on_commit=False)

        async with Session() as session:
            record = CallRecord(
                call_sid="CA_pytest_001",
                caller="+33600000001",
                direction="inbound",
                duration_secs=60.0,
                turns=3,
                transcript="Utilisateur: bonjour\nAgent: Bonjour !",
                status="completed",
                created_at=datetime.utcnow(),
            )
            session.add(record)
            await session.commit()

        async with Session() as session:
            result = await session.execute(
                select(CallRecord).where(CallRecord.call_sid == "CA_pytest_001")
            )
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.caller == "+33600000001"
            assert found.turns == 3

        await engine.dispose()


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


class TestAdminRouter:
    def test_list_calls_empty(self, client):
        with patch("app.routers.admin.get_recent_calls", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = []
            r = client.get("/admin/calls")
        assert r.status_code == 200
        assert r.json()["calls"] == []
        assert r.json()["count"] == 0

    def test_get_call_not_found(self, client):
        with patch("app.routers.admin.get_call_by_sid", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            r = client.get("/admin/calls/CA_unknown")
        assert r.status_code == 404

    def test_get_call_found(self, client):
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.call_sid = "CA_test_123"
        mock_record.caller = "+33600000001"
        mock_record.direction = "inbound"
        mock_record.duration_secs = 45.0
        mock_record.turns = 2
        mock_record.status = "completed"
        mock_record.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_record.transcript = "Utilisateur: bonjour"

        with patch("app.routers.admin.get_call_by_sid", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_record
            r = client.get("/admin/calls/CA_test_123")

        assert r.status_code == 200
        data = r.json()
        assert data["call_sid"] == "CA_test_123"
        assert data["caller"] == "+33600000001"

    def test_list_calls_with_caller_filter(self, client):
        mock_record = MagicMock()
        mock_record.id = 1
        mock_record.call_sid = "CA_001"
        mock_record.caller = "+33600000001"
        mock_record.direction = "inbound"
        mock_record.duration_secs = 30.0
        mock_record.turns = 1
        mock_record.status = "completed"
        mock_record.created_at = datetime(2026, 5, 20, 10, 0, 0)
        mock_record.transcript = ""

        with patch("app.routers.admin.get_calls_by_caller", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [mock_record]
            r = client.get("/admin/calls?caller=%2B33600000001")

        assert r.status_code == 200
        assert r.json()["count"] == 1
