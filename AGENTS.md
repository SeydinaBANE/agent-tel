# AGENTS.md — Agent Téléphonique IA

## Quick start

```bash
source .venv/bin/activate
make install-dev  # prod + dev dependencies
make dev          # uvicorn app.main:app --reload
make test         # pytest tests/ -v (with coverage — slow)
make test-unit    # pytest tests/ -v --no-cov (faster)
make lint         # ruff check app/ tests/
make format       # ruff format then ruff check --fix
make typecheck    # mypy app/ --ignore-missing-imports
make docker-build # docker build
make docker-run   # docker compose up -d
```

## Architecture

- **Entrypoint**: `app/main.py` — FastAPI with `lifespan` (async context manager), calls `init_db()` and optional Sentry init.
- **Call flow**: Twilio POST `/twiml/inbound` → returns TwiML with `<Stream>` → WebSocket `/ws/stream` → `CallSession` → mulaw audio → Whisper STT → Agno agent → TTS → mulauw → Twilio.
- **API routes**: `/health` (public), `/twiml/inbound` (Twilio-signed), `/calls/outbound` (rate-limited, 10/min/IP), `/ws/stream` (WebSocket, rate-limited per IP), `/admin/*` (X-Admin-Key header, rate-limited).
- **`CallSession`** is per-WebSocket-connection, never shared. `agent_task: asyncio.Task | None` — cancellable for barge-in.
- **Whisper model** is module-level global (`_model` in `stt.py`), loaded once at first call.
- **Twilio audio codec is mulaw 8kHz** — all audio conversions must respect this.
- **WebSocket auth**: HMAC token embedded in TwiML Stream URL via `ws_auth_secret`. Validated on connect. Empty `ws_auth_secret` → bypass (dev mode).
- **Graceful shutdown**: `cancel_all_sessions()` in lifespan yield cancels all active `CallSession` tasks.
- **Feature flags** (env vars): `LLM_STREAMING=true` (streaming LLM→TTS), `MULTI_AGENT_MODE=true` (supervisor + specialists), `ESCALATION_PHONE=+33...` (human escalation).
- **Version**: single source in `VERSION` file, read by `app/main.py`. Docker images tagged via semver git tags (`v1.2.3`) → `ghcr.io/seydinabane/agent-tel`.
- **Docker**: non-root user, healthcheck on `/health`, migrations run via `entrypoint.sh` on container start.

## Code style

- **Strict types** on all functions. No comments except non-obvious WHY.
- **All I/O is async** — no blocking calls in handlers.
- **ruff line-length = 100** (not default 88). Config in `pyproject.toml`.
- **mypy `no_strict_optional = true`** — less strict than mypy default.
- **Tool pattern**: separate pure logic (`_fn`) from Agno decorator. Tests import `_fn`; Agno uses `fn = tool(...)(_fn)`.
- **No `# type: ignore`** without documented reason. Exception: `settings = Settings()  # type: ignore[call-arg]` in `config.py` (pydantic-settings / mypy interaction).
- **All `__init__.py` files are empty** — no package-level imports or re-exports.

## Testing

- **pytest** with `asyncio_mode = auto` (async def test methods auto-detected — `@pytest.mark.asyncio` optional but still used in existing tests).
- **conftest.py** sets env vars via `os.environ.setdefault()` at module level before any imports — must maintain this order.
- **Agno agents are mocked** in tests (`create_tel_agent` / `agent.arun` as AsyncMock) to avoid real LLM calls.
- **Whisper mocked** via `_get_model` to avoid model loading.
- **Tools tested via `_fn`** (pure logic), not the decorated `fn`.
- Tests use `unittest.mock.patch` and `pytest.mocker` fixtures.
- DB tests use `tmp_path` + in-memory SQLite with explicit engine creation.

## Config quirks

- `allow_service_mocks: bool = True` in Settings — if set to `False` and CRM/Calendar not configured, server raises `RuntimeError` at startup. Individual CRM/Calendar functions also gate mock data behind this flag.
- `ADMIN_API_KEY` empty → admin routes accessible without auth (dev mode).
- `TWILIO_AUTH_TOKEN` empty → Twilio signature validation bypassed (dev mode).
- `ws_auth_secret` empty → WebSocket token validation bypassed (dev mode).
- **DB URL auto-detection** in `session.py`: `sqlite:///` → `sqlite+aiosqlite:///`, `postgresql://` → `postgresql+asyncpg://`.
- `PUBLIC_URL` must be HTTPS in production (Twilio requires `wss://`).
- `ffmpeg` must be installed on host (included in Dockerfile).
- **Required secrets** (`OPENROUTER_API_KEY`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`) validated at startup — server refuses to start if any are missing.

## Sentence splitting gotcha

`_SENTENCE_BOUNDARY` in `stream.py` and `split_sentences()` in `tts.py` use **different regex patterns** — don't assume they're the same despite similar purpose.

## Developer workflow

- `make test` includes coverage by default — use `make test-unit` for quick runs.
- `make format` runs `ruff format` then `ruff check --fix` (in that order).
- `make install-dev` installs both `requirements.txt` (prod) + `requirements-dev.txt` (ruff, mypy, pytest, pre-commit)
- Pre-commit hooks check: trailing whitespace, EOF fixer, YAML/TOML validity, large files (>500KB), merge conflicts, private keys, branch protection (`main`). Then ruff (with `--fix`), ruff-format, mypy.
