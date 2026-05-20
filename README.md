# Agent Téléphonique IA

Agent vocal intelligent entrant et sortant, construit avec **Agno** (framework agentique), **Twilio Media Streams** et **OpenRouter**. Zéro dépendance sur l'API OpenAI — STT et TTS sont gratuits.

## Fonctionnalités

- **Appels entrants** — répond automatiquement, identifie le client, traite la demande
- **Appels sortants** — déclenche des appels via API REST
- **Function calling** — calendrier, CRM, envoi de SMS
- **Temps réel** — flux audio WebSocket bidirectionnel (Twilio Media Streams)
- **STT** — Whisper local, aucune clé API requise
- **TTS** — edge-tts (Microsoft), voix française `fr-FR-DeniseNeural`, gratuit

## Architecture

```
Appelant ──► Twilio ──► WebSocket ──► FastAPI
                                          │
                                   Agno Agent (OpenRouter)
                                          │
                              ┌───────────┼───────────┐
                          Calendrier     CRM          SMS
```

## Prérequis

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) installé sur le système
- Compte [OpenRouter](https://openrouter.ai) avec une clé API
- Compte [Twilio](https://console.twilio.com) avec un numéro de téléphone actif
- [ngrok](https://ngrok.com/download) pour les tests locaux

```bash
# macOS
brew install ffmpeg ngrok

# Ubuntu
sudo apt install ffmpeg
```

## Installation

```bash
# 1. Cloner le projet
git clone <repo> && cd agent-tel

# 2. Créer et activer le venv
python3.11 -m venv .venv && source .venv/bin/activate

# 3. Installer les dépendances
make install

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés
```

## Configuration

Remplir le fichier `.env` :

```env
# OpenRouter (LLM)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openai/gpt-4o   # ou anthropic/claude-3.5-sonnet, etc.

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+33...

# URL publique (ngrok en dev, domaine en prod)
PUBLIC_URL=https://xxxx.ngrok-free.app
```

## Démarrage

```bash
# Terminal 1 — serveur
make dev

# Terminal 2 — tunnel ngrok
make ngrok
# → Copier l'URL https://xxxx.ngrok-free.app dans PUBLIC_URL du .env
```

Configurer Twilio :
- **console.twilio.com → Phone Numbers → Manage → votre numéro**
- **Voice → A call comes in** : `https://<ngrok>/twiml/inbound` → HTTP POST

## Commandes disponibles

```bash
make help        # Liste toutes les commandes
make install     # Installe les dépendances
make dev         # Serveur avec hot-reload
make run         # Serveur sans reload (prod)
make test        # 31 tests (avec coverage)
make test-unit   # Tests sans coverage (rapide)
make lint        # ruff check
make format      # ruff format + fix
make typecheck   # mypy
make hooks       # Installe pre-commit
make ngrok       # Tunnel ngrok port 8000
make clean       # Supprime __pycache__, .coverage, etc.
```

## API

| Méthode | Endpoint | Description |
|---|---|---|
| GET | `/health` | Santé du serveur |
| POST | `/twiml/inbound` | Webhook Twilio appel entrant |
| GET | `/twiml/outbound` | TwiML appel sortant |
| POST | `/calls/outbound` | Déclencher un appel sortant |
| WS | `/ws/stream` | Flux audio Media Streams |

### Déclencher un appel sortant

```bash
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"to": "+33600000001", "context": "Rappel RDV demain 10h"}'
```

## Ajouter un tool métier

```python
# app/agents/tools/mon_tool.py
from agno.tools import tool

def _mon_tool(parametre: str) -> str:
    # logique pure — facile à tester
    return "résultat"

mon_tool = tool(description="Description claire de ce que fait le tool.")(_mon_tool)
```

```python
# app/agents/tel_agent.py
from app.agents.tools.mon_tool import mon_tool
# ...
tools=[..., mon_tool]
```

## Variables d'environnement

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `OPENROUTER_API_KEY` | Oui | — | Clé API OpenRouter |
| `OPENROUTER_BASE_URL` | Non | `https://openrouter.ai/api/v1` | Base URL OpenRouter |
| `OPENROUTER_MODEL` | Non | `openai/gpt-4o` | Modèle LLM utilisé |
| `TWILIO_ACCOUNT_SID` | Oui | — | Account SID Twilio |
| `TWILIO_AUTH_TOKEN` | Oui | — | Auth Token Twilio |
| `TWILIO_PHONE_NUMBER` | Oui | — | Numéro Twilio E.164 |
| `PUBLIC_URL` | Oui | `http://localhost:8000` | URL publique du serveur |
| `APP_HOST` | Non | `0.0.0.0` | Host uvicorn |
| `APP_PORT` | Non | `8000` | Port uvicorn |
| `AGENT_VOICE` | Non | `fr-FR-DeniseNeural` | Voix edge-tts |
| `AGENT_NAME` | Non | `Assistant` | Nom affiché par l'agent |
| `AGENT_LANGUAGE` | Non | `fr` | Langue Whisper |
| `WHISPER_MODEL` | Non | `base` | Taille du modèle Whisper |

**Modèles Whisper disponibles** : `tiny` (rapide, moins précis) → `base` → `small` → `medium` → `large` (lent, très précis)

**Voix edge-tts françaises** : `fr-FR-DeniseNeural` (féminin), `fr-FR-HenriNeural` (masculin)

## Tests

```bash
make test        # 31 tests, rapport coverage terminal
make test-cov    # + rapport HTML dans htmlcov/
```

Couverture par module :

| Module | Ce qui est testé |
|---|---|
| `test_tools.py` | Logique calendar, CRM, SMS + registration Agno |
| `test_audio.py` | Conversion mulaw→WAV, Whisper mocké |
| `test_stream.py` | CallSession : buffer, énergie vocale, silence, flush |
| `test_api.py` | Tous les endpoints HTTP FastAPI |

## Licence

Usage interne.
