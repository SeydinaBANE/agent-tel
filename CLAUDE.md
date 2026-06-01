# CLAUDE.md — Agent Téléphonique IA

## Contexte du projet

Agent téléphonique IA entrant + sortant, production-ready. LLM via **OpenRouter** (interface compatible OpenAI). STT **Whisper local** (aucune clé API). TTS **edge-tts** Microsoft gratuit ou **ElevenLabs** (optionnel). Pipeline streaming LLM→TTS pour latence réduite. Multi-agents, mémoire client, escalade vers humain. Le venv est dans `.venv/` à la racine du projet.

## Stack technique

| Composant | Technologie | Version |
|---|---|---|
| Framework agentique | Agno | 2.6.8 |
| LLM | OpenRouter → GPT-4o (ou autre) | via `OpenAILike` |
| Serveur | FastAPI + Uvicorn | 0.116+ (Starlette 1.0+) |
| Téléphonie | Twilio Media Streams (WebSocket) | 9.x |
| STT | Whisper local (`openai-whisper`) | 20250625 |
| TTS | edge-tts + ffmpeg (mulaw) / ElevenLabs | 7.x |
| DB | SQLAlchemy async (SQLite / PostgreSQL) | 2.x |
| Config | pydantic-settings v2 + `.env` | 2.x |
| Tests | pytest + pytest-asyncio + pytest-mock | 126 tests |
| Qualité | ruff + mypy + pre-commit + CI GitHub Actions | — |
| Conteneurisation | Docker multi-stage + docker compose | — |

## Commandes essentielles

```bash
source .venv/bin/activate
make install          # Dépendances production
make install-dev      # Prod + dev (ruff, mypy, pytest, pre-commit)
make dev              # Serveur avec hot-reload
make test             # 126 tests avec coverage
make test-unit        # Tests sans coverage (rapide)
make lint             # ruff check
make format           # ruff format + fix
make typecheck        # mypy
make docker-build     # Construit l'image Docker
make docker-run       # docker compose up -d
make ngrok            # Tunnel ngrok port 8000
make clean            # Supprime __pycache__, .coverage, etc.
```

## Structure des fichiers clés

```
agent-tel/
├── app/
│   ├── main.py                  # FastAPI v4 : lifespan, slowapi, Sentry, admin router
│   ├── config.py                # Settings via .env (pydantic-settings v2)
│   ├── logger.py                # Logging structuré JSON (structlog)
│   ├── agents/
│   │   ├── tel_agent.py         # Agent + process_turn() + process_turn_streaming()
│   │   ├── team.py              # Multi-agents : superviseur + spécialistes
│   │   └── tools/
│   │       ├── calendar_tool.py      # check_availability, book_appointment
│   │       ├── crm_tool.py           # get_client_info, log_call_summary
│   │       ├── sms_tool.py           # send_sms
│   │       └── escalation_tool.py   # request_human_escalation
│   ├── telephony/
│   │   ├── stream.py            # CallSession + handle_media_stream + streaming pipeline
│   │   ├── inbound.py           # TwiML appels entrants
│   │   └── outbound.py          # Appels sortants REST + TwiML sortant
│   ├── services/
│   │   ├── stt.py               # Whisper local : mulaw → WAV → texte (retry x3)
│   │   ├── tts.py               # edge-tts / ElevenLabs + split_sentences + streaming
│   │   ├── escalation.py        # ESCALATION_SENTINEL + transfer_call() (Twilio REST)
│   │   ├── crm.py               # Adaptateur HTTP CRM (HubSpot/Salesforce) + mock
│   │   ├── calendar_service.py  # Google Calendar service account + mock
│   │   └── webhook.py           # Notification Slack/Teams post-appel
│   ├── db/
│   │   ├── session.py           # create_async_engine, init_db, AsyncSessionLocal
│   │   ├── models.py            # CallRecord (SQLAlchemy)
│   │   └── repository.py        # save_call, get_recent_calls, get_call_stats, ...
│   ├── middleware/
│   │   ├── twilio_auth.py       # verify_twilio_signature (Depends FastAPI)
│   │   ├── rate_limit.py        # Limiteur de débit pour les endpoints
│   │   ├── ws_limiter.py        # Rate limiting WebSocket par IP
│   │   └── admin_auth.py        # X-Admin-Key validation
│   └── routers/
│       ├── admin.py             # GET /admin/calls, /admin/calls/{sid}, /admin/metrics
│       └── ws_auth.py           # WebSocket HMAC token generation
├── tests/
│   ├── conftest.py              # Fixtures + env variables de test
│   ├── test_api.py              # Endpoints FastAPI
│   ├── test_audio.py            # Conversion mulaw + Whisper mocké
│   ├── test_stream.py           # CallSession (buffer, silence, flush)
│   ├── test_tools.py            # Tools Agno (fonctions pures + registration)
│   ├── test_websocket.py        # Flux WebSocket start→stop complet
│   ├── test_phase3.py           # CRM, Calendar, DB, Webhook, Admin API
│   ├── test_phase4.py           # Signature Twilio, rate limit, health
│   ├── test_phase5.py           # Mémoire client, escalade, métriques
│   ├── test_phase5b.py          # Streaming TTS, ElevenLabs, multi-agents
│   ├── test_llm_streaming.py    # process_turn_streaming, événements Agno
│   └── test_prod_fixes.py       # Admin auth bypass, health DB check, mock check
├── alembic/
│   ├── env.py                   # Alembic async env (SQLAlchemy async)
│   ├── script.py.mako           # Template de migration
│   └── versions/
│       └── ec21ea6bd62f_initial.py  # Migration initiale : table call_records
├── docs/
│   ├── architecture-technique.md
│   ├── deploiement.md
│   ├── api-reference.md
│   └── tests.md
├── .github/workflows/
│   └── ci.yml                   # CI : ruff, mypy, pytest, Docker build, Trivy scan
├── VERSION                      # Version courante (4.0.0)
├── Makefile                     # Commandes de développement
├── Dockerfile                   # Python 3.11-slim + ffmpeg, non-root user
├── docker-compose.yml
├── entrypoint.sh                # Migrations Alembic au démarrage
├── Dockerfile.dockerignore
├── railway.toml                 # Déploiement Railway
├── Procfile                     # Pour Railway/Heroku
├── pyproject.toml               # Config ruff, mypy, pytest, coverage
├── .env.example                 # Template complet
├── .pre-commit-config.yaml      # ruff + mypy + hooks sécurité
├── requirements.txt             # Dépendances production
├── requirements-dev.txt         # Dépendances dev (ruff, mypy, pytest, pre-commit)
├── AGENTS.md                    # gstack instructions agent
├── CONTRIBUTING.md
├── LICENSE                      # MIT
└── .trivyignore                 # Exclusions scanner Trivy
```

## Conventions de code

- **Python 3.11+** avec type hints sur toutes les fonctions
- Tout I/O est `async` — pas de blocking calls dans les handlers
- Tools Agno : **séparer la logique pure (`_fn`) du décorateur** pour la testabilité
  ```python
  def _my_tool(param: str) -> str: ...
  my_tool = tool(description="...")(_my_tool)
  ```
- Les tests importent `_fn` ; le code métier et Agno utilisent `fn`
- Pas de commentaires sauf WHY non-évident
- `ruff` line-length = 100 (pas le défaut 88). Config dans `pyproject.toml`.
- `mypy` `no_strict_optional = true` — moins strict que le mypy par défaut.
- `no # type: ignore` sans raison documentée. Exception : `settings = Settings()  # type: ignore[call-arg]` dans `config.py`.
- Tous les `__init__.py` sont vides — pas d'imports ou ré-exports au niveau package.

## Points d'attention critiques

- `CallSession` est instanciée par appel — jamais partagée entre connexions WebSocket
- Whisper charge le modèle en mémoire au premier appel (`_model` global) — ne pas recharger à chaque tour
- Le codec audio Twilio est mulaw 8kHz — toute la chaîne doit respecter ce format
- `_SENTENCE_BOUNDARY` dans `stream.py` et `split_sentences()` dans `tts.py` utilisent des regex **différentes** — ne pas supposer qu'elles sont identiques
- `PUBLIC_URL` doit être HTTPS en production (requis par Twilio pour `wss://`)
- `ffmpeg` doit être installé sur le système hôte (inclus dans le Dockerfile)
- `audioop` est déprécié en Python 3.13 — utiliser `audioop-lts` si migration vers 3.13
- FastAPI ≥ 0.116 requis — Starlette 1.0 a supprimé `on_startup` dans `Router.__init__`
- `settings = Settings()  # type: ignore[call-arg]` dans `config.py` — pydantic-settings et mypy
- Config quirks : `allow_service_mocks`, `ADMIN_API_KEY`, `TWILIO_AUTH_TOKEN`, `ws_auth_secret` vides = bypass en dev
- **Détection auto DB URL** dans `session.py` : `sqlite:///` → `sqlite+aiosqlite:///`, `postgresql://` → `postgresql+asyncpg://`

## Ajouter un tool Agno

1. Créer `app/agents/tools/mon_tool.py` :
   ```python
   from agno.tools import tool

   def _mon_tool(param: str) -> str:
       return "résultat"

   mon_tool = tool(description="Ce que fait le tool.")(_mon_tool)
   ```
2. Importer dans `app/agents/tel_agent.py` et ajouter à `tools=[..., mon_tool]`
3. Tester la logique pure via `_mon_tool(...)` dans `tests/test_tools.py`

## Activer le streaming LLM → TTS

```env
LLM_STREAMING=true          # active process_turn_streaming()
TTS_SENTENCE_STREAMING=true # déjà vrai par défaut
```

Le pipeline consomme `RunContentEvent` d'Agno, bufferise jusqu'à une frontière de phrase (`_SENTENCE_BOUNDARY`), puis TTS chaque phrase dès qu'elle est prête.

## Activer le mode multi-agents

```env
MULTI_AGENT_MODE=true
```

Crée un superviseur Agno avec deux outils de délégation vers des agents spécialistes (Calendar, CRM). Voir `app/agents/team.py`.

## Activer l'escalade vers humain

```env
ESCALATION_PHONE=+33600000002  # numéro E.164 du conseiller
```

L'agent utilise l'outil `request_human_escalation(reason)` qui retourne `ESCALATION_SENTINEL`. Le pipeline détecte le sentinel et appelle `transfer_call()` (Twilio REST mid-call).

## Changer de modèle LLM

Modifier `OPENROUTER_MODEL` dans `.env`. OpenRouter supporte :
- `openai/gpt-4o` (défaut)
- `anthropic/claude-3.5-sonnet`
- `google/gemini-2.0-flash-001`
- `meta-llama/llama-3.3-70b-instruct`

## Production — Docker

```bash
make docker-build    # build multi-stage
make docker-run      # docker compose up -d
git tag v4.0.0 && git push origin v4.0.0  # CI build automatique → ghcr.io
```

L'image utilise un **non-root user** (`app`, uid 1000), **healthcheck** `/health` toutes les 30s, et exécute **Alembic migrations** automatiquement via `entrypoint.sh`.

## Production — variables requises

Le serveur refuse de démarrer si ces clés sont absentes :
- `OPENROUTER_API_KEY`
- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`

## Tests

```bash
make test             # 126 tests, rapport coverage terminal
make test-unit        # Tests sans coverage (rapide)
```

| Fichier | Tests | Ce qui est couvert |
|---|---|---|
| `test_tools.py` | 16 | Logique calendar, CRM, SMS + registration Agno |
| `test_audio.py` | 5 | Conversion mulaw→WAV, Whisper mocké |
| `test_stream.py` | 7 | CallSession : buffer, énergie vocale, silence, flush |
| `test_api.py` | 8 | Endpoints HTTP FastAPI |
| `test_phase2.py` | 16 | E.164, timeout, barge-in, stop handler, retry, tokens |
| `test_phase3.py` | 17 | CRM, Calendar, DB, Webhook, Admin API |
| `test_phase4.py` | 9 | Signature Twilio, rate limit, health v4 |
| `test_phase5.py` | 14 | Mémoire client, escalade, langue auto, métriques |
| `test_phase5b.py` | 16 | split_sentences, ElevenLabs, multi-agents, streaming |
| `test_llm_streaming.py` | 6 | process_turn_streaming, événements Agno |
| `test_prod_fixes.py` | 10 | Admin auth, mock check, health DB |
