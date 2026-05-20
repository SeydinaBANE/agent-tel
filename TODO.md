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

## Phase 2 — Robustesse ✅

- [x] Gestion des timeouts appel (watchdog asyncio, raccrochage auto après `CALL_TIMEOUT_SECS`)
- [x] Retry automatique x3 sur erreur STT / TTS (backoff exponentiel 0.4s × attempt)
- [x] Logging structuré JSON (`app/logger.py`) — `call_sid`, durée, transcript, tous les événements
- [x] Barge-in — cancel du task TTS + `clear` Twilio quand l'utilisateur reprend la parole
- [x] Validation E.164 sur `POST /calls/outbound` (regex `^\+[1-9]\d{1,14}$`)
- [x] Tests d'intégration WebSocket — flux start → stop complet simulé
- [x] Signal `stop` Twilio → `_handle_call_end()` → résumé auto envoyé au CRM via agent
- [x] Tokens spéciaux `__START__`, `__TIMEOUT__`, `__END__` résolus dans `process_turn()`
- [x] TTS subprocess `ffmpeg` wrappé dans `asyncio.to_thread` (non-bloquant)

---

## Phase 3 — Intégrations métier ✅

- [x] Brancher le CRM réel (Salesforce / HubSpot / Notion) — adaptateur HTTP générique + mock
- [x] Brancher Google Calendar via service account — `calendar_service.py` + mock
- [x] Webhook post-appel (notifier Slack/Teams avec résumé + transcript)
- [x] Historique des appels en base de données (SQLite local / PostgreSQL prod)
- [x] Transcription complète stockée par `call_sid`
- [x] Dashboard admin REST : `GET /admin/calls`, `GET /admin/calls/{sid}`

---

## Phase 4 — Déploiement & Production ✅

- [x] Rate limiting `POST /calls/outbound` (slowapi, 10 req/min/IP configurable)
- [x] Validation signature Twilio (`X-Twilio-Signature`) — dépendance FastAPI, bypass dev automatique
- [x] Monitoring erreurs Sentry (init conditionnel si `SENTRY_DSN` configuré)
- [x] Health endpoint enrichi (`/health` avec version + statut DB)
- [x] CI/CD GitHub Actions (`.github/workflows/ci.yml`) — lint + mypy + tests sur chaque push
- [ ] Variables d'environnement dans un secrets manager (Doppler / AWS Secrets Manager)
- [ ] Déploiement Railway / Render / EC2
- [ ] Configurer domaine custom + certificat TLS (requis pour `wss://`)
- [ ] Métriques : durée d'appel, latence STT/LLM/TTS, taux d'erreur (Datadog / Grafana)
- [ ] Alertes en cas de taux d'erreur > seuil

---

## Phase 4 — Métriques (restant)

- [x] Métriques latence STT/LLM/TTS — loggées par tour (`turn_latency`, `tts_latency`)
- [x] Endpoint `GET /admin/metrics` — total appels, durée moyenne, tours moyens
- [ ] Variables d'environnement dans un secrets manager (Doppler / AWS Secrets Manager)
- [ ] Déploiement Railway / Render / EC2
- [ ] Configurer domaine custom + certificat TLS (requis pour `wss://`)
- [ ] Alertes en cas de taux d'erreur > seuil

---

## Phase 5 — Améliorations IA ✅

- [x] Mémoire persistante par client — historique des 3 derniers appels injecté dans le prompt
- [x] Escalade vers humain — outil `request_human_escalation` + transfert Twilio REST
- [x] Résumé SMS post-appel — envoyé automatiquement si `SEND_SUMMARY_SMS=true`
- [x] Détection de langue automatique — `WHISPER_LANGUAGE=` (vide = Whisper auto-détecte)
- [x] Multi-agents — superviseur + CalendarSpecialist + CRMSpecialist (`MULTI_AGENT_MODE=true`)
- [x] ElevenLabs TTS — remplace edge-tts si `ELEVENLABS_API_KEY` configuré
- [x] Streaming TTS par phrase — `split_sentences()` + `synthesize_streaming()` pour réduire first-byte latency
- [x] Streaming LLM → TTS — `process_turn_streaming()` via Agno `RunContentEvent`, pipeline `_handle_streaming_turn`, `LLM_STREAMING=true`

---

## Points de vigilance

- `audioop` est déprécié en Python 3.13 — migrer vers `audioop-lts` si upgrade Python
- Le mock CRM (`_MOCK_CRM` dans `crm_tool.py`) doit être remplacé avant mise en production
- `SILENCE_THRESHOLD` (0.8s) est à calibrer selon la qualité réseau et la langue
- Whisper `base` peut être inexact sur du bruit de fond — envisager `small` ou `medium` en prod
- `ffmpeg` doit être présent sur le système hôte (inclus dans le Dockerfile)
