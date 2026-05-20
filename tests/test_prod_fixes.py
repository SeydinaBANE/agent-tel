"""Tests pour les trois corrections bloquantes production.

1. Authentification admin (/admin/* protégé par X-Admin-Key)
2. Blocage au démarrage si ALLOW_SERVICE_MOCKS=false sans services configurés
3. Health check DB réel (try/except, pas len() >= 0)
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Fix 1 — Admin auth
# ---------------------------------------------------------------------------


class TestAdminAuth:
    def test_no_key_configured_bypasses_auth(self):
        """ADMIN_API_KEY vide → accès libre (dev)."""
        from app.main import app

        with patch("app.middleware.admin_auth.settings") as s:
            s.admin_api_key = ""
            with patch(
                "app.routers.admin.get_recent_calls", new_callable=AsyncMock, return_value=[]
            ):
                r = TestClient(app).get("/admin/calls")
        assert r.status_code == 200

    def test_wrong_key_returns_403(self):
        """Mauvaise clé → 403."""
        from app.main import app

        with patch("app.middleware.admin_auth.settings") as s:
            s.admin_api_key = "secret"
            r = TestClient(app).get("/admin/calls", headers={"X-Admin-Key": "wrong"})
        assert r.status_code == 403

    def test_missing_key_returns_403(self):
        """Clé absente quand ADMIN_API_KEY configuré → 403."""
        from app.main import app

        with patch("app.middleware.admin_auth.settings") as s:
            s.admin_api_key = "secret"
            r = TestClient(app).get("/admin/calls")
        assert r.status_code == 403

    def test_correct_key_returns_200(self):
        """Bonne clé → 200."""
        from app.main import app

        with patch("app.middleware.admin_auth.settings") as s:
            s.admin_api_key = "secret"
            with patch(
                "app.routers.admin.get_recent_calls", new_callable=AsyncMock, return_value=[]
            ):
                r = TestClient(app).get("/admin/calls", headers={"X-Admin-Key": "secret"})
        assert r.status_code == 200

    def test_metrics_also_protected(self):
        """GET /admin/metrics est également protégé."""
        from app.main import app

        with patch("app.middleware.admin_auth.settings") as s:
            s.admin_api_key = "secret"
            r = TestClient(app).get("/admin/metrics")
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Fix 2 — Blocage démarrage si mocks désactivés sans services configurés
# ---------------------------------------------------------------------------


class TestServiceMockCheck:
    def test_allow_mocks_true_starts_fine(self):
        """ALLOW_SERVICE_MOCKS=true → démarrage normal même sans CRM ni Calendar."""
        from app.main import _check_service_config

        with patch("app.main.settings") as s:
            s.allow_service_mocks = True
            s.crm_api_url = ""
            s.google_calendar_credentials = ""
            _check_service_config()  # ne doit pas lever

    def test_mocks_false_without_crm_raises(self):
        """ALLOW_SERVICE_MOCKS=false sans CRM_API_URL → RuntimeError."""
        from app.main import _check_service_config

        with patch("app.main.settings") as s:
            s.allow_service_mocks = False
            s.crm_api_url = ""
            s.google_calendar_credentials = "creds_ok"
            with pytest.raises(RuntimeError, match="CRM_API_URL"):
                _check_service_config()

    def test_mocks_false_without_calendar_raises(self):
        """ALLOW_SERVICE_MOCKS=false sans GOOGLE_CALENDAR_CREDENTIALS → RuntimeError."""
        from app.main import _check_service_config

        with patch("app.main.settings") as s:
            s.allow_service_mocks = False
            s.crm_api_url = "https://crm.example.com"
            s.google_calendar_credentials = ""
            with pytest.raises(RuntimeError, match="GOOGLE_CALENDAR_CREDENTIALS"):
                _check_service_config()

    def test_mocks_false_with_all_services_ok(self):
        """ALLOW_SERVICE_MOCKS=false avec tout configuré → démarrage normal."""
        from app.main import _check_service_config

        with patch("app.main.settings") as s:
            s.allow_service_mocks = False
            s.crm_api_url = "https://crm.example.com"
            s.google_calendar_credentials = '{"type": "service_account"}'
            _check_service_config()  # ne doit pas lever

    def test_error_message_lists_all_missing(self):
        """Le message d'erreur liste toutes les variables manquantes."""
        from app.main import _check_service_config

        with patch("app.main.settings") as s:
            s.allow_service_mocks = False
            s.crm_api_url = ""
            s.google_calendar_credentials = ""
            with pytest.raises(RuntimeError) as exc:
                _check_service_config()
        msg = str(exc.value)
        assert "CRM_API_URL" in msg
        assert "GOOGLE_CALENDAR_CREDENTIALS" in msg


# ---------------------------------------------------------------------------
# Fix 3 — Health check DB réel
# ---------------------------------------------------------------------------


class TestHealthDbCheck:
    def test_health_db_ok_when_db_works(self):
        from app.main import app

        with patch("app.main.get_recent_calls", new_callable=AsyncMock, return_value=[]):
            r = TestClient(app).get("/health")
        assert r.json()["db"] == "ok"

    def test_health_db_error_when_db_fails(self):
        """Si la DB lève une exception → db: error (pas un 500)."""
        from app.main import app

        with patch(
            "app.main.get_recent_calls", new_callable=AsyncMock, side_effect=Exception("DB down")
        ):
            r = TestClient(app).get("/health")
        assert r.status_code == 200
        assert r.json()["db"] == "error"
        assert r.json()["status"] == "ok"
