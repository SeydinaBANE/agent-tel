# Documentation Technique — Agent Téléphonique IA

## Vue d'ensemble

L'agent téléphonique est un système temps réel qui connecte les appels vocaux Twilio à un agent IA orchestré par Agno 2.6.8. Le LLM est routé via OpenRouter (interface compatible OpenAI). Le STT utilise Whisper local (aucune clé API). Le TTS utilise edge-tts Microsoft ou ElevenLabs, converti en mulaw via ffmpeg. Le flux de données est entièrement asynchrone (FastAPI + asyncio).

---

## Flux d'un appel entrant

```
1.  L'appelant compose le numéro Twilio
2.  Twilio POST /twiml/inbound → validation signature X-Twilio-Signature
3.  Serveur retourne TwiML <Connect><Stream url="wss://...">
4.  Twilio ouvre WebSocket vers /ws/stream
5.  CallSession créée : agent Agno isolé + chargement mémoire client (DB)
6.  __START__ → agent.arun() → message d'accueil → TTS → audio Twilio
7.  Twilio stream l'audio en paquets mulaw 8kHz (20ms/paquet, base64)
8.  Analyse d'énergie → détection voix / silence
9.  Après SILENCE_THRESHOLD (0.8s) de silence post-parole → transcription
10. mulaw → audioop.ulaw2lin → PCM 16-bit → ratecv 8→16kHz → WAV
11. WAV → whisper.transcribe() → texte (asyncio.to_thread)
12. Texte → process_turn() ou process_turn_streaming() → Agno
13. Réponse texte (+ appels tools si nécessaire)
14. Texte → TTS (edge-tts ou ElevenLabs) → ffmpeg → mulaw 8kHz
15. mulaw base64 → WebSocket Twilio → audio dans l'oreille de l'appelant
16. Fin d'appel : résumé DB + SMS post-appel + notification Slack/Teams
```

## Flux d'un appel sortant

```
1. POST /calls/outbound {"to": "+33...", "context": "..."} (rate limitée 10/min/IP)
2. twilio.calls.create(url=/twiml/outbound) → Twilio appelle le destinataire
3. Destinataire décroche → Twilio GET /twiml/outbound → TwiML <Connect><Stream>
4. Suite identique au flux entrant (étapes 4–16)
```

---

## Pipeline LLM Streaming → TTS

Activé par `LLM_STREAMING=true`. Réduit la latence first-audio de ~40%.

```
Agno.arun(stream=True, stream_events=True)
    │
    ├─ RunContentEvent.content  ──► buffer ──► _SENTENCE_BOUNDARY ──► phrase
    │                                                                    │
    │                                                          synthesize_speech()
    │                                                                    │
    │                                                          mulaw → Twilio
    │
    ├─ ToolCallCompletedEvent (request_human_escalation)
    │       └─ yield ("escalade", reason) → transfer_call() → Twilio REST
    │
    └─ RunCompletedEvent → flush buffer restant
```

`_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")` — découpe aux frontières de phrases.

Sans streaming, `process_turn()` fait un seul appel `agent.arun()` et attend la réponse complète.

---

## Composants détaillés

### `app/config.py` — Settings

Utilise pydantic-settings v2 (`SettingsConfigDict`). Chargé une fois au démarrage via `settings = Settings()`. Toutes les variables d'environnement sont définies ici — jamais hardcodées ailleurs.

Variables critiques : `OPENROUTER_API_KEY`, `TWILIO_*`, `PUBLIC_URL`, `DATABASE_URL`.

### `app/main.py` — Application FastAPI v4

| Route | Méthode | Auth | Rôle |
|---|---|---|---|
| `/health` | GET | — | Statut + version + DB |
| `/twiml/inbound` | POST | Twilio sig | Webhook entrant → TwiML |
| `/twiml/outbound` | GET | — | TwiML sortant |
| `/calls/outbound` | POST | rate limit | Déclenche un appel |
| `/ws/stream` | WebSocket | — | Flux audio Media Streams |
| `/admin/calls` | GET | — | Liste des appels |
| `/admin/calls/{sid}` | GET | — | Détail d'un appel |
| `/admin/metrics` | GET | — | Statistiques globales |

Lifespan : init DB → init Sentry (si DSN) → démarrage → shutdown.

### `app/telephony/stream.py` — CallSession

Classe centrale, une instance par appel WebSocket actif. Jamais partagée.

```python
class CallSession:
    call_sid: str              # Identifiant unique Twilio
    caller: str                # Numéro appelant (E.164)
    agent: Agent               # Instance Agno isolée pour cet appel
    audio_buffer: bytearray    # Buffer audio en cours
    stream_sid: str | None     # SID stream pour répondre en audio
    silence_counter: int       # Compteur de paquets silencieux
    speaking: bool             # L'utilisateur parle-t-il ?
    agent_speaking: bool       # L'agent joue-t-il de l'audio ?
    agent_task: asyncio.Task   # Tâche TTS annulable (barge-in)
    transcript: list[str]      # Historique du tour en cours
    escalation_requested: bool # Escalade demandée ?
```

**Algorithme détection fin de phrase :**
```
Pour chaque paquet audio (160 bytes, 20ms) :
  énergie = mean(|byte - 128|) pour chaque byte
  si énergie > 5 → speaking = True, silence_counter = 0
  sinon si speaking → silence_counter += 1
    si silence_counter >= (0.8s / 0.02s) = 40 → transcription
```

**Barge-in :** si `agent_speaking` ET `speaking` → `agent_task.cancel()` + `send_json({"event": "clear"})`.

**load_memory() :** fetch des 3 derniers appels en DB → recrée l'agent avec l'historique injecté dans le system prompt.

### `app/agents/tel_agent.py` — Agent Agno

```python
Agent(
    model=OpenAILike(
        id=settings.openrouter_model,       # "openai/gpt-4o" par défaut
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    ),
    tools=[
        check_availability, book_appointment,  # Google Calendar
        get_client_info, log_call_summary,      # CRM
        send_sms,                               # Twilio SMS
        request_human_escalation,              # Transfert conseiller
    ],
    instructions=SYSTEM_PROMPT + caller_context + memory_history,
    markdown=False,
)
```

Une instance par appel — isolation totale de la mémoire conversationnelle. `OpenAILike` est le connecteur Agno pour tout endpoint compatible OpenAI.

**Tokens spéciaux** (résolus avant passage au LLM) :
| Token | Résolution |
|---|---|
| `__START__` | "L'appel vient de commencer. Dis bonjour chaleureusement." |
| `__TIMEOUT__` | "L'appelant n'a plus répondu…" |
| `__END__ <résumé>` | "L'appel se termine. Remercie le client et enregistre le résumé." |

### `app/agents/team.py` — Multi-agents (MULTI_AGENT_MODE=true)

```
Superviseur Agent
    ├─ delegate_to_calendar(query) → CalendarSpecialist.arun(query)
    ├─ delegate_to_crm(query)      → CRMSpecialist.arun(query)
    ├─ send_sms
    └─ request_human_escalation
```

Les spécialistes sont des agents Agno wrappés en outils async (`@tool` decorator). Activé via `MULTI_AGENT_MODE=true`.

### `app/services/stt.py` — Speech-to-Text (Whisper local)

```
mulaw 8kHz (Twilio)
  → audioop.ulaw2lin()     # µ-law → PCM 16-bit
  → audioop.ratecv(8k→16k) # rééchantillonnage
  → wave.open() (WAV)      # encapsulation WAV en mémoire
  → whisper.transcribe()   # inférence locale (asyncio.to_thread)
  → str.strip()            # texte nettoyé
```

Modèle chargé **une seule fois** dans `_model` global au premier appel. Retry x3 avec backoff exponentiel (0.4s × attempt).

| Modèle | RAM | Précision | Vitesse |
|---|---|---|---|
| `tiny` | ~1 Go | Faible | Très rapide |
| `base` | ~1 Go | Correcte | Rapide |
| `small` | ~2 Go | Bonne | Moyen |
| `medium` | ~5 Go | Très bonne | Lent |
| `large` | ~10 Go | Excellente | Très lent |

`WHISPER_LANGUAGE` : `"fr"` par défaut. Vide = Whisper auto-détecte la langue.

### `app/services/tts.py` — Text-to-Speech

**Backend edge-tts (défaut) :**
```
texte
  → edge_tts.Communicate(text, voice)  # streaming MP3 via Microsoft
  → chunks MP3 concaténés
  → ffmpeg pipe:0 → pipe:1             # MP3 → mulaw 8kHz mono
  → bytes mulaw
```

**Backend ElevenLabs (si ELEVENLABS_API_KEY) :**
```
texte
  → POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}
  → MP3 bytes
  → ffmpeg → mulaw 8kHz
```

**Streaming TTS par phrase (TTS_SENTENCE_STREAMING=true) :**
```
texte complet
  → split_sentences()          # découpe en phrases (regex (?<=[.!?;])\s+)
  → pour chaque phrase : synthesize_speech()  # parallélisable
  → yields mulaw bytes
```

Retry x3 avec backoff exponentiel sur toutes les fonctions TTS.

### `app/agents/tools/` — Function Calling

Pattern : séparer la logique pure (`_fn`) du décorateur Agno (`fn`).

```python
def _check_availability(date: str) -> str: ...
check_availability = tool(description="...")(check_availability)
```

| Tool | Entrée | Backend | Production |
|---|---|---|---|
| `check_availability` | `date: YYYY-MM-DD` | Google Calendar | Oui (mock dev) |
| `book_appointment` | `date, time, client_name, reason` | Google Calendar | Oui (mock dev) |
| `get_client_info` | `phone_number: E.164` | CRM HTTP | Oui (mock dev) |
| `log_call_summary` | `phone_number, summary` | CRM HTTP | Oui (mock dev) |
| `send_sms` | `to: E.164, message` | Twilio SMS | Oui |
| `request_human_escalation` | `reason: str` | — | Oui (transfert Twilio) |

### `app/services/escalation.py` — Escalade vers humain

```python
ESCALATION_SENTINEL = "__ESCALADE__"

async def transfer_call(call_sid: str, reason: str) -> bool:
    twiml = f"<Response><Dial>{settings.escalation_phone}</Dial></Response>"
    await asyncio.to_thread(
        client.calls(call_sid).update, twiml=twiml
    )
```

Détection : en streaming → `ToolCallCompletedEvent` avec `tool_name == "request_human_escalation"`. En non-streaming → `ESCALATION_SENTINEL in reply`.

### `app/middleware/twilio_auth.py` — Validation Signature

```python
async def verify_twilio_signature(request: Request, ...) -> None:
    if not settings.twilio_auth_token:
        return  # bypass dev local
    signature = request.headers.get("X-Twilio-Signature", "")
    form = await request.form()
    if not validator.validate(str(request.url), dict(form), signature):
        raise HTTPException(status_code=403, detail="Signature Twilio invalide.")
```

Utilisé en `Depends` sur tous les webhooks Twilio.

### `app/db/` — Persistance

**`session.py`** : `create_async_engine` + `async_sessionmaker`. Auto-détecte SQLite (`aiosqlite`) ou PostgreSQL (`asyncpg`).

**`models.py`** : `CallRecord` — `call_sid`, `caller`, `direction`, `duration_secs`, `turns`, `transcript`, `status`, `created_at`.

**`repository.py`** :
- `save_call(...)` — appelé en fin d'appel
- `get_recent_calls(limit, offset)` — pagination
- `get_call_by_sid(sid)` — détail
- `get_calls_by_caller(caller, limit)` — historique client
- `get_call_stats()` — agrégats (total, durée moyenne, taux escalade)

---

## Format audio Twilio Media Streams

| Paramètre | Valeur |
|---|---|
| Codec | µ-law (G.711) |
| Sample rate | 8 000 Hz |
| Bit depth | 8-bit |
| Canaux | Mono |
| Taille paquet | ~160 bytes (20ms) |
| Transport | Base64 sur WebSocket JSON |

Twilio n'accepte en sortie que ce même format — toute la chaîne audio doit respecter cette contrainte.

---

## Gestion de la concurrence

Chaque WebSocket crée une `CallSession` isolée avec son propre agent Agno. FastAPI gère la concurrence via asyncio. Les opérations bloquantes sont déléguées :
- `asyncio.to_thread` → Whisper, ffmpeg, appels Twilio REST
- Tâche asyncio annulable → `_send_audio`, `_handle_streaming_turn` (barge-in)

---

## Latence estimée par tour (réseau FR)

| Étape | Sans streaming | Avec LLM_STREAMING |
|---|---|---|
| Accumulation audio | 800ms – 2s | 800ms – 2s |
| Whisper STT (`base`) | 300 – 600ms | 300 – 600ms |
| LLM (sans tool) | 600ms – 1.5s | **150ms** (première phrase) |
| TTS première phrase | 500ms – 1.2s | 500ms – 1.2s (parallèle) |
| **First audio estimé** | **2.2 – 5.3s** | **~1.6 – 4.1s** |

Pour réduire davantage : Whisper `tiny`, modèle LLM rapide (`google/gemini-2.0-flash-001`), ElevenLabs Turbo.

---

## Sécurité

| Mécanisme | Implémentation |
|---|---|
| Validation signature Twilio | `RequestValidator.validate()` en `Depends` FastAPI |
| Rate limiting | slowapi, 10 req/min/IP, `POST /calls/outbound` |
| Secrets | `.env` uniquement — `.gitignore`, jamais dans le code |
| Monitoring erreurs | Sentry SDK (init conditionnel) |
| Validation numéro | Regex E.164 `^\+[1-9]\d{1,14}$` |

---

## Qualité du code

| Outil | Rôle | Config |
|---|---|---|
| `ruff` | Linter + formatter | `pyproject.toml` → `[tool.ruff]` |
| `mypy` | Vérification de types | `pyproject.toml` → `[tool.mypy]` |
| `pre-commit` | Hooks pré-commit | `.pre-commit-config.yaml` |
| `pytest` | 114 tests | `pyproject.toml` → `[tool.pytest.ini_options]` |
| `pytest-cov` | Coverage (~70%) | `pyproject.toml` → `[tool.coverage]` |
| GitHub Actions | CI sur chaque push | `.github/workflows/ci.yml` |

Hooks pré-commit : trailing whitespace, end-of-file, check-yaml, check-merge-conflict, detect-private-key, no-commit-to-main, ruff, ruff-format, mypy.
