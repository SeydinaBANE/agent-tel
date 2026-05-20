# Documentation Technique — Agent Téléphonique IA

## Vue d'ensemble

L'agent téléphonique est un système temps réel qui connecte les appels vocaux Twilio à un agent IA orchestré par Agno. Le LLM est routé via OpenRouter. Le STT utilise Whisper local (aucune clé API). Le TTS utilise edge-tts converti en mulaw via ffmpeg. Le flux de données est entièrement asynchrone.

---

## Flux d'un appel entrant

```
1.  L'appelant compose le numéro Twilio
2.  Twilio POST /twiml/inbound → serveur retourne TwiML <Connect><Stream>
3.  Twilio ouvre WebSocket vers /ws/stream
4.  Twilio stream l'audio en paquets mulaw 8kHz (20ms/paquet, encodé base64)
5.  CallSession accumule les paquets dans audio_buffer (bytearray)
6.  Analyse d'énergie sur chaque paquet → détection voix / silence
7.  Après SILENCE_THRESHOLD (0.8s) de silence post-parole → transcription
8.  mulaw buffer → audioop.ulaw2lin → PCM 16-bit → ratecv 8→16kHz → WAV
9.  WAV → whisper.transcribe() → texte (exécuté dans asyncio.to_thread)
10. Texte → agent.arun() → réponse Agno (+ appels tools si nécessaire)
11. Réponse texte → edge-tts.Communicate → MP3 → ffmpeg → mulaw 8kHz
12. mulaw base64 → WebSocket Twilio → joué à l'appelant
```

## Flux d'un appel sortant

```
1. POST /calls/outbound {"to": "+33...", "context": "..."}
2. twilio.calls.create(url=/twiml/outbound) → Twilio appelle le destinataire
3. Destinataire décroche → Twilio GET /twiml/outbound → TwiML <Connect><Stream>
4. Suite identique au flux entrant (étapes 3–12)
```

---

## Composants détaillés

### `app/config.py` — Settings

Utilise pydantic-settings v2 (`SettingsConfigDict`). Chargé une fois au démarrage. Toute modification du `.env` nécessite un redémarrage.

Variables critiques : `OPENROUTER_API_KEY`, `TWILIO_*`, `PUBLIC_URL`.

### `app/main.py` — Routeur FastAPI

| Route | Méthode | Rôle |
|---|---|---|
| `/health` | GET | Santé du service |
| `/twiml/inbound` | POST | Webhook Twilio → TwiML entrant |
| `/twiml/outbound` | GET | TwiML pour appels sortants |
| `/calls/outbound` | POST | Déclenche un appel via Twilio REST |
| `/ws/stream` | WebSocket | Flux audio Media Streams |

### `app/telephony/stream.py` — CallSession

Classe centrale, une instance par appel WebSocket actif.

```python
class CallSession:
    call_sid: str           # Identifiant unique Twilio
    caller: str             # Numéro appelant (E.164)
    agent: Agent            # Instance Agno isolée pour cet appel
    audio_buffer: bytearray # Buffer audio en cours
    stream_sid: str | None  # SID stream pour répondre en audio
    silence_counter: int    # Compteur de paquets silencieux
    speaking: bool          # L'utilisateur est-il en train de parler ?
```

**Algorithme de détection de fin de phrase :**

```
Pour chaque paquet audio (160 bytes, 20ms) :
  énergie = mean(|byte - 128|) pour chaque byte
  si énergie > 5 :
    speaking = True, silence_counter = 0
  sinon si speaking :
    silence_counter += 1
    si silence_counter >= (SILENCE_THRESHOLD / CHUNK_DURATION) :
      → déclenchement transcription
```

`SILENCE_THRESHOLD = 0.8s`, `CHUNK_DURATION = 0.02s` → seuil = 40 paquets silencieux.

### `app/agents/tel_agent.py` — Agent Agno

Une instance d'`Agent` par appel — isolation totale de la mémoire conversationnelle entre les appels.

```python
Agent(
    model=OpenAILike(
        id=settings.openrouter_model,       # ex: "openai/gpt-4o"
        api_key=settings.openrouter_api_key,
        base_url="https://openrouter.ai/api/v1",
    ),
    tools=[check_availability, book_appointment, get_client_info, log_call_summary, send_sms],
    instructions=SYSTEM_PROMPT + caller_context,
    markdown=False,   # sortie vocale — pas de markdown
)
```

`OpenAILike` est le connecteur Agno pour tout endpoint compatible OpenAI. OpenRouter expose cette interface.

### `app/services/stt.py` — Speech-to-Text (Whisper local)

**Pipeline :**
```
mulaw 8kHz (Twilio)
  → audioop.ulaw2lin()     # µ-law → PCM 16-bit
  → audioop.ratecv(8k→16k) # rééchantillonnage
  → wave.open() (WAV)      # encapsulation WAV
  → whisper.transcribe()   # inférence locale (asyncio.to_thread)
  → str.strip()            # texte nettoyé
```

Le modèle Whisper est chargé **une seule fois** dans `_model` global au premier appel. Les appels suivants réutilisent le modèle en mémoire.

Modèles disponibles (config `WHISPER_MODEL`) :

| Modèle | RAM | Précision | Vitesse |
|---|---|---|---|
| `tiny` | ~1 Go | Faible | Très rapide |
| `base` | ~1 Go | Correcte | Rapide |
| `small` | ~2 Go | Bonne | Moyen |
| `medium` | ~5 Go | Très bonne | Lent |
| `large` | ~10 Go | Excellente | Très lent |

### `app/services/tts.py` — Text-to-Speech (edge-tts)

**Pipeline :**
```
texte
  → edge_tts.Communicate(text, voice)  # streaming MP3 via Microsoft
  → chunks MP3 concaténés
  → ffmpeg pipe:0 → pipe:1             # MP3 → mulaw 8kHz mono
  → bytes mulaw                        # prêt pour Twilio
```

`ffmpeg` gère la conversion de format en une seule passe. Voix configurables via `AGENT_VOICE` (défaut : `fr-FR-DeniseNeural`).

### `app/agents/tools/` — Function Calling

**Pattern de structure :**
```python
# Logique pure (testable sans Agno)
def _check_availability(date: str) -> str:
    ...

# Registration Agno (objet Function)
check_availability = tool(description="...")(check_availability)
```

Les tests importent `_fn` pour tester la logique pure ; l'agent Agno utilise `fn` (objet `Function`).

| Tool | Entrée | Sortie |
|---|---|---|
| `check_availability` | `date: YYYY-MM-DD` | Créneaux libres |
| `book_appointment` | `date, time, client_name, reason` | Confirmation + ID |
| `get_client_info` | `phone_number: E.164` | Nom, compte, dernier contact |
| `log_call_summary` | `phone_number, summary` | Confirmation |
| `send_sms` | `to: E.164, message` | SID Twilio |

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

Twilio n'accepte en sortie que ce même format — toute la chaîne audio (STT et TTS) doit respecter cette contrainte.

---

## Gestion de la concurrence

Chaque connexion WebSocket crée une `CallSession` isolée avec son propre agent Agno. FastAPI gère la concurrence via asyncio. Les opérations bloquantes (Whisper, ffmpeg) sont déléguées à `asyncio.to_thread` / `subprocess.run` pour ne pas bloquer la boucle événementielle.

---

## Qualité du code

| Outil | Rôle | Config |
|---|---|---|
| `ruff` | Linter + formatter | `pyproject.toml` → `[tool.ruff]` |
| `mypy` | Vérification de types | `pyproject.toml` → `[tool.mypy]` |
| `pre-commit` | Hooks pre-commit | `.pre-commit-config.yaml` |
| `pytest` | Tests (31) | `pyproject.toml` → `[tool.pytest.ini_options]` |
| `pytest-cov` | Coverage | `pyproject.toml` → `[tool.coverage]` |

Hooks pre-commit actifs : trailing whitespace, end-of-file, check-yaml, check-merge-conflict, detect-private-key, no-commit-to-main, ruff, ruff-format, mypy.

---

## Latence estimée par tour (réseau FR)

| Étape | Durée estimée |
|---|---|
| Accumulation audio (parole) | 800ms – 2s |
| Whisper STT (modèle `base`) | 300 – 600ms |
| OpenRouter LLM (sans tool) | 600ms – 1.5s |
| OpenRouter LLM (avec tool) | 1s – 3s |
| edge-tts + ffmpeg | 500ms – 1.2s |
| **Total estimé** | **2.2 – 8.2s** |

Pour réduire : passer Whisper à `tiny`, utiliser un modèle LLM rapide (`google/gemini-2.0-flash-001`), implémenter le streaming TTS (Phase 5).

---

## Sécurité

### Validation signature Twilio (Phase 4 — à implémenter)

```python
from twilio.request_validator import RequestValidator

validator = RequestValidator(settings.twilio_auth_token)
is_valid = validator.validate(request_url, form_params, signature_header)
if not is_valid:
    raise HTTPException(status_code=403)
```

### Secrets

- Toutes les clés dans `.env` uniquement — jamais dans le code source
- `.env` et `.venv/` dans `.gitignore`
- En production : secrets manager (Doppler, AWS Secrets Manager, Railway Secrets)
