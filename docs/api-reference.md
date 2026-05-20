# Référence API

Base URL : `http://localhost:8000` (local) · `https://votre-domaine.com` (production)

---

## GET /health

Vérifie que le serveur est opérationnel, retourne la version et le statut de la base de données.

**Réponse 200**
```json
{
  "status": "ok",
  "version": "4.0.0",
  "db": "ok"
}
```

`"db": "error"` si la base de données est inaccessible (le serveur reste opérationnel).

---

## POST /twiml/inbound

Webhook Twilio déclenché à chaque appel entrant. Retourne un TwiML `<Connect><Stream>` qui connecte l'appel au WebSocket Media Streams.

**Sécurité** : valide la signature `X-Twilio-Signature` (bypass automatique en dev si `TWILIO_AUTH_TOKEN` non configuré).

**Appelé par** : Twilio (ne pas appeler manuellement en production)

**Body** — `application/x-www-form-urlencoded` (envoyé par Twilio)

| Champ | Type | Description |
|---|---|---|
| `From` | string | Numéro de l'appelant (E.164) |
| `CallSid` | string | Identifiant unique de l'appel Twilio |
| `To` | string | Numéro Twilio composé |

**Réponse 200** — `application/xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://votre-domaine.com/ws/stream">
      <Parameter name="caller" value="+33600000001"/>
    </Stream>
  </Connect>
</Response>
```

**Réponse 403** — signature Twilio invalide
```json
{"detail": "Signature Twilio invalide."}
```

---

## GET /twiml/outbound

TwiML pour les appels sortants. Appelé automatiquement par Twilio quand le destinataire décroche.

**Appelé par** : Twilio (ne pas appeler manuellement)

**Query parameters**

| Paramètre | Type | Description |
|---|---|---|
| `caller` | string | Numéro appelé (E.164, encodé `%2B33...`) |
| `context` | string | Contexte optionnel transmis à l'agent |

**Exemple**
```
GET /twiml/outbound?caller=%2B33600000001&context=Rappel+RDV
```

**Réponse 200** — `application/xml`
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://votre-domaine.com/ws/stream">
      <Parameter name="caller" value="+33600000001"/>
      <Parameter name="context" value="Rappel RDV"/>
    </Stream>
  </Connect>
</Response>
```

---

## POST /calls/outbound

Déclenche un appel téléphonique sortant via l'API Twilio REST.

**Rate limit** : 10 requêtes/minute/IP (configurable via `RATE_LIMIT_CALLS_PER_MINUTE`).

**Body** — `application/json`

| Champ | Type | Requis | Description |
|---|---|---|---|
| `to` | string | Oui | Numéro à appeler (E.164, ex: `+33600000001`) |
| `context` | string | Non | Contexte transmis à l'agent |

**Exemple**
```bash
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+33600000001",
    "context": "Rappel RDV demain à 10h avec Alice Martin"
  }'
```

**Réponse 200 — succès**
```json
{
  "call_sid": "CA1234567890abcdef1234567890abcdef",
  "to": "+33600000001",
  "status": "initiated"
}
```

**Réponse 200 — numéro manquant ou invalide**
```json
{
  "error": "Le champ 'to' est requis (numéro E.164)"
}
```

**Réponse 429 — rate limit dépassé**
```json
{
  "error": "Rate limit exceeded: 10 per 1 minute"
}
```

---

## WebSocket /ws/stream

Flux audio bidirectionnel Twilio Media Streams. Géré automatiquement par Twilio — ce WebSocket est ouvert par Twilio, pas par le client HTTP.

**Protocole** : WebSocket — `ws://` (local), `wss://` (production, obligatoire pour Twilio)

---

### Messages Twilio → Serveur

**Événement `start`** — reçu une fois, au début de l'appel

```json
{
  "event": "start",
  "start": {
    "callSid": "CA...",
    "streamSid": "MZ...",
    "customParameters": {
      "caller": "+33600000001",
      "context": "Rappel RDV"
    }
  }
}
```

À la réception : création d'une `CallSession`, chargement de l'historique client (DB), envoi du message d'accueil (`__START__`).

---

**Événement `media`** — reçu en continu (~50 paquets/seconde)

```json
{
  "event": "media",
  "media": {
    "payload": "<base64-mulaw-8kHz-160bytes>"
  }
}
```

Chaque paquet = 160 bytes = 20ms d'audio mulaw 8kHz mono.

---

**Événement `stop`** — reçu en fin d'appel (raccrochage)

```json
{
  "event": "stop"
}
```

Déclenche `_handle_call_end()` : persistance DB, SMS récap, notification Slack/Teams.

---

### Messages Serveur → Twilio

**Envoyer de l'audio** (réponse vocale de l'agent)

```json
{
  "event": "media",
  "streamSid": "MZ...",
  "media": {
    "payload": "<base64-mulaw-8kHz>"
  }
}
```

**Interrompre l'audio** (barge-in ou timeout)

```json
{
  "event": "clear",
  "streamSid": "MZ..."
}
```

---

## GET /admin/calls

Liste paginée des appels enregistrés.

**Query parameters**

| Paramètre | Défaut | Description |
|---|---|---|
| `limit` | `20` | Nombre max de résultats (1–100) |
| `offset` | `0` | Décalage pour la pagination |
| `caller` | — | Filtrer par numéro appelant |

**Exemple**
```bash
# 20 derniers appels
curl http://localhost:8000/admin/calls

# Appels du numéro +33600000001
curl "http://localhost:8000/admin/calls?caller=%2B33600000001"
```

**Réponse 200**
```json
{
  "calls": [
    {
      "id": 42,
      "call_sid": "CA...",
      "caller": "+33600000001",
      "direction": "inbound",
      "duration_secs": 87.3,
      "turns": 4,
      "status": "completed",
      "created_at": "2026-05-20T10:30:00",
      "transcript": "Utilisateur: Bonjour\nAgent: Bonjour, comment puis-je..."
    }
  ],
  "count": 1
}
```

---

## GET /admin/calls/{call_sid}

Détail complet d'un appel par son `call_sid`.

**Exemple**
```bash
curl http://localhost:8000/admin/calls/CA1234567890abcdef
```

**Réponse 200** — même format que les items de `/admin/calls`

**Réponse 404**
```json
{"detail": "Appel 'CA...' introuvable."}
```

---

## GET /admin/metrics

Statistiques agrégées sur tous les appels enregistrés.

**Exemple**
```bash
curl http://localhost:8000/admin/metrics
```

**Réponse 200**
```json
{
  "total_calls": 42,
  "avg_duration_secs": 87.3,
  "avg_turns": 4.1,
  "escalation_rate": 0.07,
  "completed_calls": 39,
  "escalated_calls": 3
}
```

---

## Codes HTTP

| Code | Description |
|---|---|
| 200 | Succès |
| 403 | Signature Twilio invalide |
| 404 | Ressource introuvable (admin) |
| 422 | Erreur de validation Pydantic (body JSON malformé) |
| 429 | Rate limit dépassé |
| 500 | Erreur serveur interne non gérée |

Les erreurs WebSocket sont loguées côté serveur avec le `call_sid` associé et n'ont pas de code HTTP.

---

## Logs structurés JSON

Tous les événements sont loggés en JSON avec `structlog`. Champs principaux :

| Événement | Champs clés |
|---|---|
| `call_started` | `call_sid`, `caller` |
| `user_speech` | `call_sid`, `text` |
| `turn_latency` | `call_sid`, `stt_ms`, `llm_ms` |
| `turn_latency_streaming` | `call_sid`, `stt_ms`, `llm_first_sentence_ms` |
| `tts_latency` | `call_sid`, `tts_ms`, `chunks` |
| `agent_reply` | `call_sid`, `text` |
| `barge_in` | `call_sid` |
| `call_timeout` | `call_sid`, `idle_secs` |
| `call_ended` | `call_sid`, `caller`, `duration_secs`, `turns`, `escalated` |
| `summary_sms_sent` | `call_sid`, `caller` |
