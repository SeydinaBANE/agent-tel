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
| Tests | pytest + pytest-asyncio + pytest-mock | 114 tests |
| Qualité | ruff + mypy + pre-commit + CI GitHub Actions | — |

## Commandes essentielles

```bash
# Activer le venv local
source .venv/bin/activate

# Installer les dépendances
make install

# Lancer le serveur en développement (avec reload)
make dev

# Lancer tous les tests
make test

# Linter + formatter
make lint
make format

# Tunnel ngrok pour Twilio
make ngrok

# Installer les hooks pre-commit
make hooks
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
│   │   └── twilio_auth.py       # verify_twilio_signature (Depends FastAPI)
│   └── routers/
│       └── admin.py             # GET /admin/calls, /admin/calls/{sid}, /admin/metrics
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
│   └── test_llm_streaming.py    # process_turn_streaming, événements Agno
├── docs/
│   ├── architecture-technique.md
│   ├── deploiement.md
│   ├── api-reference.md
│   └── tests.md
├── .github/workflows/ci.yml    # CI : ruff, mypy, pytest sur chaque push
├── railway.toml                 # Déploiement Railway (Dockerfile + healthcheck)
├── .venv/                       # Venv local Python 3.11
├── .env                         # Variables d'environnement (non commité)
├── .env.example                 # Template complet
├── .pre-commit-config.yaml      # ruff + mypy + hooks sécurité
├── pyproject.toml               # Config ruff, mypy, pytest, coverage
├── Makefile                     # Commandes de développement
├── Dockerfile                   # Python 3.11-slim + ffmpeg
├── docker-compose.yml
└── Procfile                     # Pour Railway/Heroku
```

## Conventions de code

- **Python 3.11+** avec type hints sur toutes les fonctions
- Tout I/O est `async` — pas de blocking calls dans les handlers
- Tools Agno : **séparer la logique pure (`_fn`) du décorateur** pour la testabilité
  ```python
  def _my_tool(param: str) -> str: ...
  my_tool = tool(description="...")(my_tool)
  ```
- Les tests importent `_fn` ; le code métier et Agno utilisent `fn`
- Pas de commentaires sauf WHY non-évident

## Points d'attention critiques

- `CallSession` est instanciée par appel — jamais partagée entre connexions WebSocket
- Whisper charge le modèle en mémoire au premier appel (`_model` global) — ne pas recharger à chaque tour
- Le codec audio Twilio est mulaw 8kHz — toute la chaîne doit respecter ce format
- `PUBLIC_URL` doit être HTTPS en production (requis par Twilio pour `wss://`)
- `ffmpeg` doit être installé sur le système hôte (inclus dans le Dockerfile)
- `audioop` est déprécié en Python 3.13 — utiliser `audioop-lts` si migration vers 3.13
- FastAPI ≥ 0.116 requis — Starlette 1.0 a supprimé `on_startup` dans `Router.__init__`
- `settings = Settings()  # type: ignore[call-arg]` dans `config.py` — pydantic-settings et mypy

## Ajouter un tool Agno

1. Créer `app/agents/tools/mon_tool.py` :
   ```python
   from agno.tools import tool

   def _mon_tool(param: str) -> str:
       return "résultat"

   mon_tool = tool(description="Ce que fait le tool.")(mon_tool)
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
