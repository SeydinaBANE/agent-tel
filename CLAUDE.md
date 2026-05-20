# CLAUDE.md — Agent Téléphonique IA

## Contexte du projet

Agent téléphonique IA entrant + sortant. Le LLM est routé via **OpenRouter** (compatible OpenAI SDK). Le STT utilise **Whisper local** (aucune clé API, modèle téléchargé à la première invocation). Le TTS utilise **edge-tts** (Microsoft, gratuit) converti en mulaw via `ffmpeg`. Le venv est dans `.venv/` à la racine du projet.

## Stack technique

| Composant | Technologie | Version |
|---|---|---|
| Framework agentique | Agno | 2.6.8 |
| LLM | OpenRouter → GPT-4o (ou autre) | via `OpenAILike` |
| Serveur | FastAPI + Uvicorn | 0.116+ (Starlette 1.0+) |
| Téléphonie | Twilio Media Streams (WebSocket) | 9.x |
| STT | Whisper local (`openai-whisper`) | 20250625 |
| TTS | edge-tts + ffmpeg (mulaw) | 7.x |
| Config | pydantic-settings v2 + `.env` | 2.x |
| Tests | pytest + pytest-asyncio + pytest-mock | 114 tests |
| Qualité | ruff + mypy + pre-commit | — |

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
│   ├── main.py              # Routes FastAPI (webhooks Twilio + WebSocket)
│   ├── config.py            # Settings via .env (pydantic-settings v2)
│   ├── agents/
│   │   ├── tel_agent.py     # Agent Agno — OpenAILike(OpenRouter) + process_turn()
│   │   └── tools/           # Function calling tools
│   │       ├── calendar_tool.py  # _check_availability, _book_appointment
│   │       ├── crm_tool.py       # _get_client_info, _log_call_summary
│   │       └── sms_tool.py       # _send_sms
│   ├── telephony/
│   │   ├── stream.py        # CallSession + handle_media_stream (WebSocket)
│   │   ├── inbound.py       # TwiML appels entrants
│   │   └── outbound.py      # Appels sortants REST + TwiML sortant
│   └── services/
│       ├── stt.py           # Whisper local : mulaw → WAV → texte
│       └── tts.py           # edge-tts : texte → MP3 → ffmpeg → mulaw 8kHz
├── tests/
│   ├── conftest.py          # Fixtures + env variables de test
│   ├── test_api.py          # Endpoints FastAPI (TestClient)
│   ├── test_audio.py        # Conversion mulaw + Whisper mocké
│   ├── test_stream.py       # CallSession (buffer, silence, flush)
│   └── test_tools.py        # Tools Agno (fonctions pures + registration)
├── docs/
│   ├── architecture-technique.md
│   ├── deploiement.md
│   └── api-reference.md
├── .venv/                   # Venv local Python 3.11
├── .env                     # Variables d'environnement (non commité)
├── .env.example             # Template
├── .pre-commit-config.yaml  # ruff + mypy + hooks sécurité
├── pyproject.toml           # Config ruff, mypy, pytest, coverage
├── Makefile                 # Commandes de développement
├── Dockerfile               # Image Python 3.11-slim + ffmpeg
├── docker-compose.yml
└── Procfile                 # Pour Railway/Heroku
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

## Changer de modèle LLM

Modifier `OPENROUTER_MODEL` dans `.env`. OpenRouter supporte :
- `openai/gpt-4o` (défaut)
- `anthropic/claude-3.5-sonnet`
- `google/gemini-2.0-flash-001`
- `meta-llama/llama-3.3-70b-instruct`
