# Référence API

Base URL : `http://localhost:8000` (local) · `https://votre-domaine.com` (production)

---

## GET /health

Vérifie que le serveur est opérationnel.

**Réponse 200**
```json
{"status": "ok"}
```

---

## POST /twiml/inbound

Webhook Twilio déclenché à chaque appel entrant. Retourne un TwiML `<Connect><Stream>` qui connecte l'appel au WebSocket Media Streams.

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

---

## GET /twiml/outbound

TwiML pour les appels sortants. Appelé automatiquement par Twilio quand le destinataire décroche.

**Appelé par** : Twilio (ne pas appeler manuellement)

**Query parameters**

| Paramètre | Type | Description |
|---|---|---|
| `caller` | string | Numéro appelé — doit être encodé `%2B33...` (le `+` en URL) |
| `context` | string | Contexte optionnel transmis à l'agent (ex: motif de l'appel) |

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

**Body** — `application/json`

| Champ | Type | Requis | Description |
|---|---|---|---|
| `to` | string | Oui | Numéro à appeler (E.164, ex: `+33600000001`) |
| `context` | string | Non | Contexte transmis à l'agent (ex: motif, instructions spéciales) |

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

**Réponse 200 — champ `to` manquant**
```json
{
  "error": "Le champ 'to' est requis (numéro E.164)"
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

À la réception, le serveur crée une `CallSession` et envoie le message d'accueil.

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

L'audio doit impérativement être en mulaw 8kHz mono, encodé base64.

---

## Codes HTTP

| Code | Description |
|---|---|
| 200 | Succès (toutes les routes retournent 200, même les erreurs métier) |
| 422 | Erreur de validation Pydantic (body JSON malformé) |
| 500 | Erreur serveur interne non gérée |

Les erreurs WebSocket sont loguées côté serveur avec le `call_sid` associé — elles ne retournent pas de code HTTP.
