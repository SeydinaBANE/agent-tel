import os
import pytest

# Variables d'env factices pour éviter les erreurs de validation pydantic-settings
os.environ.setdefault("OPENROUTER_API_KEY", "sk-or-test-key")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "ACtest")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "test_token")
os.environ.setdefault("TWILIO_PHONE_NUMBER", "+33000000000")
os.environ.setdefault("PUBLIC_URL", "http://localhost:8000")


@pytest.fixture
def fake_mulaw_audio() -> bytes:
    """128 octets de silence mulaw (valeur 0xFF = silence en µ-law)."""
    return bytes([0xFF] * 3200)  # ~200ms @ 8kHz mulaw


@pytest.fixture
def sample_phone() -> str:
    return "+33600000001"
