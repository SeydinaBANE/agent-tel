# Agent Téléphonique IA

![CI](https://github.com/SeydinaBANE/agent-tel/actions/workflows/ci.yml/badge.svg)
![Docker](https://img.shields.io/badge/docker-ghcr.io/seydinabane/agent--tel-blue?logo=docker)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116+-green)
![Agno](https://img.shields.io/badge/Agno-2.6.8-purple)
![Tests](https://img.shields.io/badge/tests-126%20passed-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-71%25-yellow)
![License](https://img.shields.io/badge/license-MIT-green)

Agent vocal intelligent entrant et sortant, construit avec **Agno 2.6.8**, **Twilio Media Streams** et **OpenRouter**. STT Whisper local (gratuit, aucune clé API). TTS edge-tts Microsoft (gratuit) ou ElevenLabs (optionnel).

**Version** : `4.0.0` — Image Docker : `ghcr.io/seydinabane/agent-tel`

---

## Fonctionnalités

### Téléphonie
- **Appels entrants** — répond automatiquement, identifie le client, traite la demande
- **Appels sortants** — déclenche des appels via API REST (`POST /calls/outbound`)
- **Barge-in** — l'utilisateur peut interrompre l'agent à tout moment
- **Timeout automatique** — raccrochage poli après inactivité configurable

### Agent IA
- **Function calling** — calendrier (Google Calendar), CRM (HubSpot/Salesforce/Notion), SMS
- **Mémoire client** — historique des 3 derniers appels injecté dans le prompt
- **Escalade vers humain** — transfert Twilio REST mid-call via outil `request_human_escalation`
- **Multi-agents** — mode superviseur + CalendarSpecialist + CRMSpecialist (`MULTI_AGENT_MODE=true`)
- **Détection de langue auto** — Whisper auto-détecte si `WHISPER_LANGUAGE` est vide

### Performance
- **Streaming LLM → TTS** — pipeline token par token, latence first-audio réduite de ~40% (`LLM_STREAMING=true`)
- **Streaming TTS par phrase** — synthèse vocale dès la première phrase (`TTS_SENTENCE_STREAMING=true`)
- **ElevenLabs TTS** — backend haute qualité si `ELEVENLABS_API_KEY` configuré

### Production
- **Validation signature Twilio** — protection de tous les webhooks (`X-Twilio-Signature`)
- **Auth WebSocket** — token HMAC signé sur `/ws/stream` via `ws_auth_secret`
- **Rate limiting** — 10 req/min/IP sur `POST /calls/outbound` + WebSocket par IP + admin 30/min
- **Monitoring Sentry** — init conditionnel si `SENTRY_DSN` configuré
- **Secrets validation** — démarrage bloqué si `OPENROUTER_API_KEY`, `TWILIO_*` manquants
- **Base de données** — SQLite locale / PostgreSQL prod, migrations Alembic
- **Dashboard admin** — `GET /admin/calls`, `GET /admin/metrics`
- **Résumé SMS post-appel** — récap envoyé automatiquement (`SEND_SUMMARY_SMS=true`)
- **Notification Slack/Teams** — webhook post-appel configurable
- **CI/CD GitHub Actions** — ruff + mypy + 126 tests + build Docker + scan Trivy
- **Arrêt gracieux** — annulation des appels en cours à l'extinction

---

## Architecture

```
Appelant ──► Twilio ──► WebSocket ──► FastAPI
                                           │
                                    CallSession
                                           │
                               ┌───────────┼────────────────┐
                          Agno Agent   Mémoire DB       Timeout WD
                               │
                   ┌───────────┼───────────┬──────────────┐
               Calendrier     CRM         SMS         Escalade
                   │           │
            Google Cal.   HubSpot/SF     Twilio REST → Conseiller
```

**Mode streaming LLM → TTS :**
```
Agno RunContentEvent ──► buffer ──► phrase ──► synthesize_speech ──► Twilio audio
```

---

## Prérequis

- Python 3.11+
- [ffmpeg](https://ffmpeg.org/download.html) installé sur le système
- Compte [OpenRouter](https://openrouter.ai) avec une clé API
- Compte [Twilio](https://console.twilio.com) avec un numéro de téléphone actif
- [ngrok](https://ngrok.com/download) pour les tests locaux
- Docker (optionnel, pour l'image conteneurisée)

```bash
# macOS
brew install ffmpeg ngrok

# Ubuntu
sudo apt install ffmpeg
```

---

## Installation

```bash
# 1. Cloner le projet
git clone https://github.com/SeydinaBANE/agent-tel.git && cd agent-tel

# 2. Créer et activer le venv
python3.11 -m venv .venv && source .venv/bin/activate

# 3. Installer les dépendances (prod)
make install

# ou tout en un (prod + dev)
make install-dev

# 4. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env avec vos clés
```

## Configuration minimale

```env
OPENROUTER_API_KEY=sk-or-...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+33...
PUBLIC_URL=https://xxxx.ngrok-free.app
DATABASE_URL=sqlite:///./calls.db
```

Voir le tableau complet des variables plus bas.

---

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

---

## Docker

```bash
# Construire l'image
make docker-build

# Lancer avec docker compose
make docker-run

# Taguer et pusher vers GHCR (via GitHub Actions)
git tag v4.0.0
git push origin v4.0.0
# → Build automatique sur ghcr.io/seydinabane/agent-tel
```

L'image inclut :
- **Non-root user** (`app`, uid 1000)
- **Healthcheck** sur `/health` toutes les 30s
- **Migrations automatiques** via `alembic upgrade head` au démarrage
- **Scan sécurité** Trivy dans le workflow CI

---

## Commandes disponibles

```bash
make help          # Liste toutes les commandes
make install       # Installe les dépendances production
make install-dev   # Installe prod + dev (ruff, mypy, pytest, pre-commit)
make dev           # Serveur avec hot-reload
make run           # Serveur sans reload (prod)
make test          # 126 tests (avec coverage)
make test-unit     # Tests sans coverage (rapide)
make lint          # ruff check
make format        # ruff format + fix
make typecheck     # mypy
make hooks         # Installe pre-commit
make docker-build  # Construit l'image Docker
make docker-run    # docker compose up -d
make ngrok         # Tunnel ngrok port 8000
make clean         # Supprime __pycache__, .coverage, etc.
```

---

## API

| Méthode | Endpoint | Description | Auth |
|---|---|---|---|
| GET | `/health` | Santé + version + statut DB | — |
| POST | `/twiml/inbound` | Webhook Twilio appel entrant | Signature HMAC |
| GET | `/twiml/outbound` | TwiML appel sortant | — |
| POST | `/calls/outbound` | Déclencher un appel sortant | Rate limit 10/min |
| WS | `/ws/stream` | Flux audio Media Streams | Token HMAC |
| GET | `/admin/calls` | Liste des appels (pagination) | X-Admin-Key |
| GET | `/admin/calls/{sid}` | Détail d'un appel | X-Admin-Key |
| GET | `/admin/metrics` | Statistiques agrégées | X-Admin-Key |

### Déclencher un appel sortant

```bash
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"to": "+33600000001", "context": "Rappel RDV demain 10h"}'
```

### Dashboard admin

```bash
curl -H "X-Admin-Key: votre-clé" http://localhost:8000/admin/calls
curl -H "X-Admin-Key: votre-clé" http://localhost:8000/admin/calls/CA1234...
curl -H "X-Admin-Key: votre-clé" http://localhost:8000/admin/metrics
```

---

## Ajouter un tool métier

```python
# app/agents/tools/mon_tool.py
from agno.tools import tool

def _mon_tool(parametre: str) -> str:
    return "résultat"

mon_tool = tool(description="Description claire.")(_mon_tool)
```

```python
# app/agents/tel_agent.py
from app.agents.tools.mon_tool import mon_tool
tools=[..., mon_tool]
```

---

## Variables d'environnement

### Requises

| Variable | Description |
|---|---|
| `OPENROUTER_API_KEY` | Clé API OpenRouter |
| `TWILIO_ACCOUNT_SID` | Account SID Twilio |
| `TWILIO_AUTH_TOKEN` | Auth Token Twilio |
| `TWILIO_PHONE_NUMBER` | Numéro Twilio E.164 |
| `PUBLIC_URL` | URL HTTPS publique du serveur |

### Agent & STT/TTS

| Variable | Défaut | Description |
|---|---|---|
| `OPENROUTER_MODEL` | `openai/gpt-4o` | Modèle LLM (OpenRouter) |
| `AGENT_VOICE` | `fr-FR-DeniseNeural` | Voix edge-tts |
| `AGENT_NAME` | `Assistant` | Nom de l'agent |
| `AGENT_LANGUAGE` | `fr` | Langue de l'agent |
| `WHISPER_MODEL` | `base` | Taille du modèle Whisper |
| `WHISPER_LANGUAGE` | `fr` | Langue STT (vide = auto-détection) |

### Fonctionnalités optionnelles

| Variable | Défaut | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./calls.db` | URL base de données |
| `SLACK_WEBHOOK_URL` | — | Webhook Slack/Teams post-appel |
| `CRM_API_URL` | — | URL API CRM (HubSpot, Salesforce…) |
| `CRM_API_KEY` | — | Clé API CRM |
| `GOOGLE_CALENDAR_CREDENTIALS` | — | JSON service account (une ligne) |
| `GOOGLE_CALENDAR_ID` | `primary` | ID calendrier Google |
| `ESCALATION_PHONE` | — | Numéro E.164 du conseiller humain |
| `SEND_SUMMARY_SMS` | `false` | SMS récap à l'appelant en fin d'appel |
| `ELEVENLABS_API_KEY` | — | Clé ElevenLabs (remplace edge-tts) |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | ID voix ElevenLabs |
| `SENTRY_DSN` | — | DSN Sentry pour le monitoring |
| `ADMIN_API_KEY` | — | Clé requise pour `/admin/*` |
| `WS_AUTH_SECRET` | — | Secret HMAC pour l'auth WebSocket |

### Performance & mode

| Variable | Défaut | Description |
|---|---|---|
| `TTS_SENTENCE_STREAMING` | `true` | Synthèse vocale phrase par phrase |
| `LLM_STREAMING` | `false` | Pipeline LLM→TTS token par token |
| `MULTI_AGENT_MODE` | `false` | Mode superviseur + spécialistes |
| `CALL_TIMEOUT_SECS` | `30` | Délai avant raccrochage automatique |
| `RATE_LIMIT_CALLS_PER_MINUTE` | `10` | Rate limit `/calls/outbound` |
| `ALLOW_SERVICE_MOCKS` | `true` | `false` → exige CRM/Calendar configurés |

**Modèles Whisper** : `tiny` (rapide) → `base` → `small` → `medium` → `large` (précis)

**Voix edge-tts françaises** : `fr-FR-DeniseNeural` (féminin), `fr-FR-HenriNeural` (masculin)

---

## Tests

```bash
make test        # 126 tests, rapport coverage terminal
make test-cov    # + rapport HTML dans htmlcov/
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

---

## Licence

MIT — voir [LICENSE](LICENSE).
