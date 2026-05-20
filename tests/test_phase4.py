"""Tests Phase 4 — Production : signature Twilio, rate limiting, health enrichi."""

import hashlib
import hmac
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


# ---------------------------------------------------------------------------
# Middleware Twilio — validation de signature
# ---------------------------------------------------------------------------


def _make_twilio_signature(auth_token: str, url: str, params: dict) -> str:
    """Reproduit l'algorithme de signature Twilio (HMAC-SHA1)."""
    s = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    return hmac.new(auth_token.encode(), s.encode(), hashlib.sha1).digest().hex()


class TestTwilioSignature:
    def test_missing_signature_returns_403(self, client):
        # TWILIO_AUTH_TOKEN non vide → la validation s'active
        with patch("app.middleware.twilio_auth.settings") as mock_settings:
            mock_settings.twilio_auth_token = "secret_token"
            response = client.post(
                "/twiml/inbound",
                data={"From": "+33600000001", "CallSid": "CA123"},
            )
        assert response.status_code == 403

    def test_no_token_configured_bypasses_check(self, client):
        """Si TWILIO_AUTH_TOKEN est vide → mode dev, pas de vérification."""
        with patch("app.middleware.twilio_auth.settings") as mock_settings:
            mock_settings.twilio_auth_token = ""
            response = client.post(
                "/twiml/inbound",
                data={"From": "+33600000001", "CallSid": "CA123"},
            )
        assert response.status_code == 200

    def test_dependency_override_bypasses_in_tests(self, client):
        """Les tests peuvent override la dépendance pour simplifier les fixtures."""
        from app.main import app
        from app.middleware.twilio_auth import verify_twilio_signature

        app.dependency_overrides[verify_twilio_signature] = lambda: None
        try:
            response = client.post(
                "/twiml/inbound",
                data={"From": "+33600000001"},
            )
            assert response.status_code == 200
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Rate limiting — POST /calls/outbound
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def test_outbound_within_limit(self, client):
        with patch("app.main.initiate_outbound_call", return_value="CA_FAKE"):
            response = client.post("/calls/outbound", json={"to": "+33600000001"})
        assert response.status_code == 200

    def test_invalid_number_not_rate_limited(self, client):
        response = client.post("/calls/outbound", json={"to": "not-e164"})
        assert response.status_code == 200
        assert "error" in response.json()


# ---------------------------------------------------------------------------
# Health endpoint enrichi
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_includes_version(self, client):
        with patch("app.main.get_recent_calls", new_callable=AsyncMock, return_value=[]):
            response = client.get("/health")
        data = response.json()
        assert "version" in data
        assert data["version"] == "4.0.0"

    def test_health_includes_db_status(self, client):
        with patch("app.main.get_recent_calls", new_callable=AsyncMock, return_value=[]):
            response = client.get("/health")
        assert "db" in response.json()
        assert response.json()["db"] == "ok"


# ---------------------------------------------------------------------------
# Config Phase 4 — nouveaux champs
# ---------------------------------------------------------------------------


class TestConfigPhase4:
    def test_sentry_dsn_defaults_empty(self):
        from app.config import settings

        assert settings.sentry_dsn == ""

    def test_rate_limit_default(self):
        from app.config import settings

        assert settings.rate_limit_calls_per_minute == 10
