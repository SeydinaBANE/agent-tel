"""Tests des endpoints FastAPI."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_ok(self, client):
        with patch("app.main.get_recent_calls", new_callable=AsyncMock, return_value=[]):
            response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestInboundTwiml:
    """La validation de signature est bypassée en test (TWILIO_AUTH_TOKEN = 'test_token',
    mais RequestValidator.validate retourne True quand le token est un placeholder court)."""

    def _post_inbound(self, client):
        # Bypass la dépendance Twilio signature pour les tests
        from app.main import app
        from app.middleware.twilio_auth import verify_twilio_signature

        app.dependency_overrides[verify_twilio_signature] = lambda: None
        try:
            return client.post(
                "/twiml/inbound",
                data={"From": "+33600000001", "CallSid": "CA123"},
            )
        finally:
            app.dependency_overrides.clear()

    def test_returns_xml(self, client):
        response = self._post_inbound(client)
        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]

    def test_twiml_contains_stream(self, client):
        response = self._post_inbound(client)
        assert "<Stream" in response.text
        assert "/ws/stream" in response.text

    def test_twiml_passes_caller_param(self, client):
        response = self._post_inbound(client)
        assert "+33600000001" in response.text


class TestOutboundTwiml:
    def test_returns_xml(self, client):
        response = client.get("/twiml/outbound?caller=+33600000001")

        assert response.status_code == 200
        assert "application/xml" in response.headers["content-type"]

    def test_contains_stream_with_caller(self, client):
        # Le + doit être encodé en %2B dans l'URL pour ne pas être interprété comme espace
        response = client.get("/twiml/outbound?caller=%2B33600000001&context=RDV")

        assert "<Stream" in response.text
        assert "33600000001" in response.text


class TestOutboundCallEndpoint:
    def test_missing_to_returns_error(self, client):
        response = client.post("/calls/outbound", json={})

        assert response.status_code == 200
        assert "error" in response.json()

    def test_valid_call_returns_sid(self, client):
        with patch("app.main.initiate_outbound_call", return_value="CA_FAKE_SID"):
            response = client.post(
                "/calls/outbound",
                json={"to": "+33600000001", "context": "Test"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["call_sid"] == "CA_FAKE_SID"
        assert data["to"] == "+33600000001"
        assert data["status"] == "initiated"
