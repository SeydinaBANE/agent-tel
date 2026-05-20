# TODO — Agent Téléphonique IA

Légende : ✅ Fait | ⬜ À faire | 🔥 Priorité haute

---

## Phase 1 — Fondations ✅

- [x] Structure du projet (FastAPI + Agno + Twilio)
- [x] Agent Agno avec OpenRouter (`OpenAILike`) + function calling
- [x] WebSocket Twilio Media Streams (flux audio temps réel)
- [x] STT — Whisper local (`openai-whisper`, aucune clé API)
- [x] TTS — edge-tts + ffmpeg (mulaw 8kHz, voix fr-FR-DeniseNeural)
- [x] Appels entrants (TwiML + WebSocket)
- [x] Appels sortants (API REST + Twilio)
- [x] Tools Agno : Calendrier (mock), CRM (mock), SMS (Twilio)
- [x] Config centralisée via `.env` + pydantic-settings v2
- [x] Venv local `.venv/` dans le projet
- [x] 31 tests (pytest + pytest-asyncio + pytest-mock)
- [x] Qualité code : ruff + mypy + pre-commit
- [x] Makefile avec toutes les commandes dev
- [x] Documentation complète (README, architecture, déploiement, API)
- [x] Dockerfile + docker-compose + Procfile

---

## Phase 2 — Robustesse 🔥

- [ ] Gestion des timeouts appel (raccrocher proprement si silence > 30s)
- [ ] Retry automatique sur erreur STT / TTS / LLM
- [ ] Logging structuré JSON avec `call_sid`, durée d'appel, transcript complet
- [ ] Gestion des interruptions (barge-in — couper le TTS si l'utilisateur reprend la parole)
- [ ] Validation format E.164 sur l'endpoint `/calls/outbound`
- [ ] Tests d'intégration — simulation complète flux WebSocket entrant
- [ ] Gestion propre du signal `stop` Twilio (log call summary auto)

---

## Phase 3 — Intégrations métier

- [ ] Brancher le CRM réel (Salesforce / HubSpot / Notion)
- [ ] Brancher Google Calendar via OAuth2
- [ ] Webhook post-appel (notifier Slack/Teams avec résumé + transcript)
- [ ] Historique des appels en base de données (PostgreSQL ou Supabase)
- [ ] Transcription complète stockée par `call_sid`
- [ ] Dashboard admin (liste des appels, écoute, métriques)

---

## Phase 4 — Déploiement & Production

- [ ] Variables d'environnement dans un secrets manager (Doppler / AWS Secrets Manager)
- [ ] Déploiement Railway / Render / EC2 avec CI/CD
- [ ] Configurer domaine custom + certificat TLS (requis pour `wss://`)
- [ ] Rate limiting sur les endpoints publics (slowapi)
- [ ] Validation signature Twilio (`X-Twilio-Signature`) sur tous les webhooks
- [ ] Monitoring erreurs (Sentry)
- [ ] Métriques : durée d'appel, latence STT/LLM/TTS, taux d'erreur (Datadog / Grafana)
- [ ] Alertes en cas de taux d'erreur > seuil

---

## Phase 5 — Améliorations IA

- [ ] Mémoire persistante par client (Agno Memory + base de données)
- [ ] Multi-agents : superviseur + agents spécialisés par domaine métier
- [ ] Escalade vers humain si demande hors périmètre (transfert d'appel Twilio)
- [ ] Résumé automatique post-appel envoyé par email/SMS
- [ ] Voix personnalisée avec ElevenLabs (remplacement edge-tts)
- [ ] Détection de langue automatique (Whisper `language=None`)
- [ ] Streaming TTS pour réduire la latence (chunked audio)
- [ ] Streaming LLM (tokens en temps réel → TTS au fil de l'eau)

---

## Points de vigilance

- `audioop` est déprécié en Python 3.13 — migrer vers `audioop-lts` si upgrade Python
- Le mock CRM (`_MOCK_CRM` dans `crm_tool.py`) doit être remplacé avant mise en production
- `SILENCE_THRESHOLD` (0.8s) est à calibrer selon la qualité réseau et la langue
- Whisper `base` peut être inexact sur du bruit de fond — envisager `small` ou `medium` en prod
- `ffmpeg` doit être présent sur le système hôte (inclus dans le Dockerfile)
