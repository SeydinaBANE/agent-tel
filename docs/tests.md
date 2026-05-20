# Guide des Tests

## Lancer les tests

```bash
make test         # 31 tests + coverage terminal
make test-unit    # 31 tests sans coverage (plus rapide)
make test-cov     # 31 tests + rapport HTML (htmlcov/index.html)
```

## Résultat attendu

```
31 passed, 1 warning in ~3s
```

Le warning `audioop deprecated` est normal sur Python 3.11 — ignoré.

---

## Organisation

```
tests/
├── conftest.py       # Fixtures partagées + env variables de test
├── test_api.py       # Endpoints FastAPI
├── test_audio.py     # Conversion audio mulaw + Whisper mocké
├── test_stream.py    # CallSession : buffer, détection vocale, flush
└── test_tools.py     # Tools Agno : logique pure + enregistrement
```

---

## `conftest.py` — Fixtures

**`fake_mulaw_audio`** — 3200 bytes de silence mulaw (0xFF = silence µ-law), soit ~200ms à 8kHz. Utilisé par `test_audio.py` et `test_stream.py`.

**`sample_phone`** — `+33600000001`, numéro de test standard.

Les variables d'environnement obligatoires sont définies via `os.environ.setdefault` pour que pydantic-settings ne lève pas d'erreur de validation au chargement de l'app.

---

## `test_api.py` — Endpoints FastAPI

Utilise `TestClient` de Starlette (synchrone, pas besoin d'asyncio).

| Test | Ce qui est vérifié |
|---|---|
| `test_health_returns_ok` | `GET /health` → `{"status": "ok"}` |
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

Whisper est mocké via `mocker.patch("app.services.stt._get_model")` — aucun modèle n'est chargé en mémoire pendant les tests.

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

**Stratégie** : les tests importent les fonctions privées `_fn` (logique pure), pas les objets `Function` Agno. Cela permet de tester sans instancier Agno ou appeler un LLM.

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

`_twilio` est mocké via `unittest.mock.patch` — aucun SMS réel envoyé.

---

## Ajouter un test

```python
# tests/test_mon_module.py
import pytest
from unittest.mock import patch, MagicMock


class TestMonModule:
    def test_cas_nominal(self):
        from app.agents.tools.mon_tool import _mon_tool

        result = _mon_tool("param")

        assert "attendu" in result

    async def test_cas_async(self, mocker):
        mocker.patch("app.services.stt._get_model", return_value=MagicMock(...))
        from app.services.stt import transcribe_audio

        result = await transcribe_audio(b"\xff" * 1600)

        assert isinstance(result, str)
```

Les tests `async def` sont automatiquement gérés par `pytest-asyncio` (mode `auto` configuré dans `pyproject.toml`).
