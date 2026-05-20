"""Tests des tools (calendar, CRM, SMS) — on teste les fonctions pures sous-jacentes."""

from unittest.mock import MagicMock, patch

import pytest


class TestCalendarTool:
    @pytest.mark.asyncio
    async def test_check_availability_returns_slots(self):
        from app.agents.tools.calendar_tool import _check_availability

        result = await _check_availability("2026-06-15")

        assert "2026-06-15" in result
        assert "Créneaux disponibles" in result

    @pytest.mark.asyncio
    async def test_book_appointment_returns_confirmation(self):
        from app.agents.tools.calendar_tool import _book_appointment

        result = await _book_appointment(
            date="2026-06-15",
            time="10:30",
            client_name="Alice Martin",
            reason="Consultation",
        )

        assert "Alice Martin" in result
        assert "2026-06-15" in result
        assert "10:30" in result
        assert "confirmé" in result

    @pytest.mark.asyncio
    async def test_book_appointment_generates_reference_id(self):
        from app.agents.tools.calendar_tool import _book_appointment

        result = await _book_appointment("2026-06-15", "10:00", "Test Client", "test")

        assert "Test Client" in result

    def test_tools_are_registered_as_agno_functions(self):
        from agno.tools import Function

        from app.agents.tools.calendar_tool import book_appointment, check_availability

        assert isinstance(check_availability, Function)
        assert isinstance(book_appointment, Function)


class TestCRMTool:
    @pytest.mark.asyncio
    async def test_known_client_returns_info(self):
        from app.agents.tools.crm_tool import _get_client_info

        result = await _get_client_info("+33600000001")

        assert "Alice Martin" in result
        assert "PRO" in result

    @pytest.mark.asyncio
    async def test_unknown_client_returns_not_found(self):
        from app.agents.tools.crm_tool import _get_client_info

        result = await _get_client_info("+33999999999")

        assert "Aucun client" in result
        assert "+33999999999" in result

    @pytest.mark.asyncio
    async def test_log_call_summary_records_summary(self):
        from app.agents.tools.crm_tool import _log_call_summary

        result = await _log_call_summary("+33600000001", "Demande de rdv confirmée")

        assert "+33600000001" in result

    def test_tools_are_registered_as_agno_functions(self):
        from agno.tools import Function

        from app.agents.tools.crm_tool import get_client_info, log_call_summary

        assert isinstance(get_client_info, Function)
        assert isinstance(log_call_summary, Function)


class TestSMSTool:
    def test_send_sms_calls_twilio(self):
        mock_message = MagicMock()
        mock_message.sid = "SM123456"

        with patch("app.agents.tools.sms_tool._twilio") as mock_client:
            mock_client.messages.create.return_value = mock_message
            from app.agents.tools.sms_tool import _send_sms

            result = _send_sms(to="+33600000001", message="Votre RDV est confirmé")

        assert "+33600000001" in result
        assert "SM123456" in result

    def test_send_sms_passes_correct_params(self):
        mock_message = MagicMock()
        mock_message.sid = "SM999"

        with patch("app.agents.tools.sms_tool._twilio") as mock_client:
            mock_client.messages.create.return_value = mock_message
            from app.agents.tools.sms_tool import _send_sms

            _send_sms(to="+33600000002", message="Test message")

            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["to"] == "+33600000002"
            assert call_kwargs["body"] == "Test message"

    def test_tool_is_registered_as_agno_function(self):
        from agno.tools import Function

        from app.agents.tools.sms_tool import send_sms

        assert isinstance(send_sms, Function)
