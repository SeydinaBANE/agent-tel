# Guide des Tests

## Lancer les tests

```bash
make test         # 114 tests + coverage terminal
make test-unit    # 114 tests sans coverage (plus rapide)
make test-cov     # 114 tests + rapport HTML (htmlcov/index.html)
```

## Résultat attendu

```
114 passed, 1 warning in ~4s
Coverage: 70%
```

Le warning `audioop deprecated` est normal sur Python 3.11 — ignoré.

---

## Organisation

```
tests/
├── conftest.py             # Fixtures partagées + env variables de test
├── test_api.py             # Endpoints FastAPI (8 tests)
├── test_audio.py           # Conversion audio mulaw + Whisper mocké (5 tests)
├── test_stream.py          # CallSession : buffer, détection vocale, flush (7 tests)
├── test_tools.py           # Tools Agno : logique pure + enregistrement (16 tests)
├── test_websocket.py       # Flux WebSocket start→stop complet (10 tests)
├── test_phase3.py          # CRM, Calendar, DB, Webhook, Admin API (17 tests)
├── test_phase4.py          # Signature Twilio, rate limit, health (9 tests)
├── test_phase5.py          # Mémoire client, escalade, métriques (14 tests)
├── test_phase5b.py         # split_sentences, ElevenLabs, multi-agents (16 tests)
└── test_llm_streaming.py   # process_turn_streaming, RunContentEvent (6 tests)
```

---

## `conftest.py` — Fixtures

**`fake_mulaw_audio`** — 3200 bytes de silence mulaw (0xFF), ~200ms à 8kHz.

**`sample_phone`** — `+33600000001`, numéro de test standard.

**`client`** — `TestClient` FastAPI avec `dependency_overrides` pour bypasser la validation signature Twilio et le chargement DB.

Les variables d'environnement obligatoires sont définies via `os.environ.setdefault` avant l'import de l'app.

---

## `test_api.py` — Endpoints FastAPI

| Test | Ce qui est vérifié |
|---|---|
| `test_health_returns_ok` | `GET /health` → `{"status": "ok"}` avec DB mockée |
| `test_returns_xml` (inbound) | Content-Type `application/xml` |
| `test_twiml_contains_stream` | Présence de `<Stream` et `/ws/stream` |
| `test_twiml_passes_caller_param` | Numéro caller dans la réponse XML |
| `test_returns_xml` (outbound) | Content-Type `application/xml` |
| `test_contains_stream_with_caller` | `%2B` encode correctement le `+` |
| `test_missing_to_returns_error` | Champ `to` absent → message d'erreur |
| `test_valid_call_returns_sid` | `initiate_outbound_call` mocké → SID retourné |

---

## `test_audio.py` — Conversion audio

| Test | Ce qui est vérifié |
|---|---|
| `test_output_is_valid_wav` | WAV valide : 1 canal, 16-bit, 16kHz |
| `test_output_is_non_empty` | Taille > 44 bytes (header WAV) |
| `test_resampling_doubles_samples` | 8kHz→16kHz ≈ double les échantillons |
| `test_transcribe_returns_string` | Whisper mocké → texte stripé |
| `test_transcribe_handles_empty_result` | Texte vide → chaîne vide |

Whisper est mocké via `mocker.patch("app.services.stt._get_model")` — aucun modèle chargé en mémoire.

---

## `test_stream.py` — CallSession

| Test | Ce qui est vérifié |
|---|---|
| `test_initial_state` | Buffer vide, speaking=False, silence_counter=0 |
| `test_add_speech_sets_speaking` | Bytes à 0x00 → énergie élevée → speaking=True |
| `test_add_silence_after_speech_increments_counter` | 0x80 post-parole → silence_counter++ |
| `test_should_not_transcribe_when_silent_from_start` | Jamais parlé → pas de transcription |
| `test_should_transcribe_after_silence_threshold` | Seuil atteint → should_transcribe()==True |
| `test_flush_returns_buffer_and_resets_state` | flush() vide le buffer et reset l'état |
| `test_audio_accumulates_in_buffer` | Deux paquets → 320 bytes dans le buffer |

`create_tel_agent` est mocké pour éviter tout appel réseau.

---

## `test_tools.py` — Tools Agno

**Stratégie** : importer `_fn` (logique pure), pas les objets `Function` Agno.

| Test | Ce qui est vérifié |
|---|---|
| `test_check_availability_*` | Date dans le résultat, créneaux présents |
| `test_book_appointment_*` | Nom, date, heure, préfixe `RDV-` |
| `test_tools_are_registered_as_agno_functions` | `isinstance(tool, Function)` |
| `test_known_client_returns_info` | Alice Martin + type PRO |
| `test_unknown_client_returns_not_found` | Message "Aucun client" |
| `test_log_call_summary_*` | Numéro + résumé dans la réponse |
| `test_send_sms_calls_twilio` | `_twilio.messages.create` appelé |
| `test_send_sms_passes_correct_params` | `to` et `body` corrects |
| `test_escalation_returns_sentinel` | Résultat contient `ESCALATION_SENTINEL` |
| `test_escalation_includes_reason` | Raison transmise dans la réponse |

`_twilio` est mocké — aucun SMS réel envoyé.

---

## `test_phase3.py` — Intégrations métier

| Groupe | Tests |
|---|---|
| CRM HTTP | Adapter retourne les données, fallback mock, erreur réseau gérée |
| Google Calendar | Créneaux mock, service account désactivé en test |
| Base de données | `save_call`, `get_recent_calls`, `get_call_by_sid` avec DB SQLite in-memory |
| Webhook | `notify_call_ended` → POST HTTP mocké |
| Admin API | `GET /admin/calls`, `GET /admin/calls/{sid}`, `GET /admin/metrics` |

---

## `test_phase4.py` — Sécurité & production

| Test | Ce qui est vérifié |
|---|---|
| `test_invalid_signature_returns_403` | Mauvaise signature → 403 |
| `test_valid_signature_passes` | Bonne signature → 200 |
| `test_no_token_bypass` | Sans `TWILIO_AUTH_TOKEN` → bypass automatique |
| `test_rate_limit_outbound` | 11e requête → 429 |
| `test_invalid_number_not_rate_limited` | Numéro invalide → 200 (erreur métier, pas 429) |
| `test_health_includes_version` | Réponse contient `"version"` |
| `test_health_includes_db_status` | Réponse contient `"db"` |

---

## `test_phase5.py` — IA avancée

| Test | Ce qui est vérifié |
|---|---|
| `test_agent_created_with_memory` | `_format_memory()` injecte l'historique dans les instructions |
| `test_memory_format_includes_date_and_duration` | Format lisible : date, durée, transcript |
| `test_escalation_sentinel_detected` | `ESCALATION_SENTINEL` déclenche le transfert |
| `test_escalation_in_reply_triggers_transfer` | `transfer_call` appelé une fois |
| `test_whisper_language_passed` | `WHISPER_LANGUAGE` transmis à `whisper.transcribe` |
| `test_metrics_endpoint` | `GET /admin/metrics` → total, avg_duration, avg_turns |

---

## `test_phase5b.py` — Streaming & multi-agents

| Groupe | Tests |
|---|---|
| `split_sentences` | Coupe sur `.`, `!`, `?`, `;` — fusionne fragments courts |
| TTS streaming | `synthesize_streaming` yield un chunk par phrase |
| ElevenLabs | Appel HTTP mocké, MP3 → ffmpeg → mulaw |
| Multi-agents | `create_team_agent` crée superviseur avec 2 outils de délégation |
| Délégation | `delegate_to_calendar` appelle `calendar_agent.arun()` |

---

## `test_llm_streaming.py` — Pipeline LLM streaming

| Test | Ce qui est vérifié |
|---|---|
| `test_special_token_yields_single_text` | `__START__` → un seul yield `("text", ...)` |
| `test_streams_sentences_from_tokens` | `RunContentEvent` → phrases reconstituées |
| `test_detects_escalation_tool_call` | `ToolCallCompletedEvent` → yield `("escalade", ...)` |
| `test_remaining_buffer_yielded_on_completion` | Buffer non-terminé flushed sur `RunCompletedEvent` |
| `test_llm_streaming_default_false` | `settings.llm_streaming` vaut `False` par défaut |
| `test_sentence_boundary_regex` | `_SENTENCE_BOUNDARY` découpe correctement 3 phrases |

---

## Ajouter un test

```python
# tests/test_mon_module.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestMonModule:
    def test_cas_nominal(self):
        from app.agents.tools.mon_tool import _mon_tool

        result = _mon_tool("param")

        assert "attendu" in result

    @pytest.mark.asyncio
    async def test_cas_async(self, mocker):
        mocker.patch("app.services.stt._get_model", return_value=MagicMock(
            transcribe=MagicMock(return_value={"text": "bonjour"})
        ))
        from app.services.stt import transcribe_audio

        result = await transcribe_audio(b"\xff" * 1600)

        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_avec_mock_agent(self):
        from app.agents.tel_agent import process_turn

        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Réponse de l'agent"
        mock_agent.arun = AsyncMock(return_value=mock_response)

        result = await process_turn(mock_agent, "Bonjour")

        assert "Réponse" in result
```

Les tests `async def` sont gérés automatiquement par `pytest-asyncio` (mode `auto` dans `pyproject.toml`).

Pour bypasser la signature Twilio dans les tests HTTP :
```python
from app.middleware.twilio_auth import verify_twilio_signature
app.dependency_overrides[verify_twilio_signature] = lambda: None
```
