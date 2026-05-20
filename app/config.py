from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # OpenRouter (LLM)
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o"

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_phone_number: str

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_url: str = "http://localhost:8000"

    # Agent
    agent_voice: str = "fr-FR-DeniseNeural"
    agent_name: str = "Assistant"
    agent_language: str = "fr"
    whisper_model: str = "base"

    # Appel
    call_timeout_secs: int = 30  # silence max avant raccrochage automatique
    max_retries: int = 3  # tentatives max sur STT / TTS / LLM

    # Base de données
    database_url: str = "sqlite:///./calls.db"

    # Notifications Slack / Teams (optionnel)
    slack_webhook_url: str = ""

    # CRM HTTP (optionnel — HubSpot / Salesforce / Notion)
    crm_api_url: str = ""
    crm_api_key: str = ""

    # Google Calendar (optionnel — JSON service account en base64 ou raw)
    google_calendar_credentials: str = ""
    google_calendar_id: str = "primary"

    # Monitoring (optionnel)
    sentry_dsn: str = ""

    # Rate limiting (requêtes/minute par IP sur POST /calls/outbound)
    rate_limit_calls_per_minute: int = 10


settings = Settings()  # type: ignore[call-arg]
