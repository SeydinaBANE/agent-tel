# Manuel de Déploiement

## Environnements

| Environnement | Objectif | Outil recommandé |
|---|---|---|
| Local | Développement, debug | uvicorn + ngrok |
| Staging | Validation avant prod | Railway / Render |
| Production | Appels réels | Railway / Docker / EC2 |

---

## 1. Déploiement local (développement)

### Prérequis système

```bash
# Python 3.11+
python3 --version

# ffmpeg (obligatoire pour la conversion TTS)
brew install ffmpeg       # macOS
sudo apt install ffmpeg   # Ubuntu

# ngrok
brew install ngrok        # macOS
# ou : https://ngrok.com/download
```

### Étapes complètes

```bash
# 1. Cloner le projet
git clone <repo> && cd agent-tel

# 2. Créer le venv local
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Installer les dépendances
make install

# 4. Configurer l'environnement
cp .env.example .env
# Éditer .env : OPENROUTER_API_KEY, TWILIO_*, PUBLIC_URL, DATABASE_URL

# 5. Lancer le serveur (terminal 1)
make dev
# → Serveur disponible sur http://localhost:8000

# 6. Ouvrir le tunnel ngrok (terminal 2)
make ngrok
# → Copier l'URL https://xxxx.ngrok-free.app

# 7. Mettre à jour PUBLIC_URL dans .env
# PUBLIC_URL=https://xxxx.ngrok-free.app

# 8. Redémarrer le serveur (Ctrl+C puis make dev)
```

### Configurer Twilio (local)

1. Aller sur [console.twilio.com](https://console.twilio.com)
2. **Phone Numbers → Manage → Active numbers → cliquer sur votre numéro**
3. Section **Voice & Fax** :
   - **A call comes in** : Webhook → `https://xxxx.ngrok-free.app/twiml/inbound` → HTTP POST
4. Sauvegarder

### Vérifier

```bash
# Santé du serveur
curl http://localhost:8000/health
# → {"status": "ok", "version": "4.0.0", "db": "ok"}

# Déclencher un appel sortant test
curl -X POST http://localhost:8000/calls/outbound \
  -H "Content-Type: application/json" \
  -d '{"to": "+33600000001", "context": "Test appel sortant"}'

# Statistiques admin
curl http://localhost:8000/admin/metrics
```

---

## 2. Déploiement Railway (recommandé)

Railway gère nativement Python, WebSocket, PostgreSQL et les variables d'environnement. `railway.toml` est déjà présent dans le repo.

### Prérequis

```bash
npm install -g @railway/cli
railway login
```

### Étapes

```bash
# 1. Initialiser le projet Railway (première fois)
railway init

# 2. Configurer les variables d'environnement — requises
railway variables set OPENROUTER_API_KEY=sk-or-...
railway variables set OPENROUTER_MODEL=openai/gpt-4o
railway variables set TWILIO_ACCOUNT_SID=AC...
railway variables set TWILIO_AUTH_TOKEN=...
railway variables set TWILIO_PHONE_NUMBER=+33...
railway variables set AGENT_NAME=Assistant
railway variables set AGENT_LANGUAGE=fr
railway variables set AGENT_VOICE=fr-FR-DeniseNeural
railway variables set WHISPER_MODEL=base
railway variables set DATABASE_URL=postgresql+asyncpg://...  # ou ajoutez un plugin PostgreSQL Railway

# 3. Variables optionnelles selon vos besoins
railway variables set SLACK_WEBHOOK_URL=https://hooks.slack.com/...
railway variables set SENTRY_DSN=https://...@sentry.io/...
railway variables set ESCALATION_PHONE=+33600000002
railway variables set SEND_SUMMARY_SMS=true
railway variables set LLM_STREAMING=true
railway variables set TTS_SENTENCE_STREAMING=true

# 4. Déployer (Railway détecte le Dockerfile automatiquement)
railway up

# 5. Récupérer l'URL publique
railway open
# → Ex: https://agent-tel-production.up.railway.app

# 6. Mettre à jour PUBLIC_URL
railway variables set PUBLIC_URL=https://agent-tel-production.up.railway.app

# 7. Redéployer avec la bonne PUBLIC_URL
railway up
```

### `railway.toml` (déjà dans le repo)

```toml
[build]
builder = "dockerfile"

[deploy]
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
```

### Ajouter PostgreSQL sur Railway

1. Dashboard Railway → **New** → **Database** → **PostgreSQL**
2. Le `DATABASE_URL` est automatiquement injecté dans l'app

### Configurer Twilio sur Railway

Webhook : `https://agent-tel-production.up.railway.app/twiml/inbound` (HTTP POST)

---

## 3. Déploiement Docker

Le `Dockerfile` et `docker-compose.yml` sont déjà dans le repo.

### Lancer avec docker-compose

```bash
# Créer et remplir le .env
cp .env.example .env
# Éditer .env avec vos clés

# Build + démarrage
docker-compose up -d

# Logs en temps réel
docker-compose logs -f agent

# Arrêter
docker-compose down
```

### Build manuel

```bash
docker build -t agent-tel .
docker run -d --env-file .env -p 8000:8000 agent-tel
```

### Contenu du Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`ffmpeg` est installé dans l'image — aucune configuration supplémentaire nécessaire.

---

## 4. Déploiement sur VPS (Ubuntu 22.04)

### Installation

```bash
# Mise à jour système
sudo apt update && sudo apt upgrade -y

# Python 3.11 + ffmpeg
sudo apt install python3.11 python3.11-venv python3-pip ffmpeg -y

# Cloner le projet
git clone <repo> /opt/agent-tel
cd /opt/agent-tel

# Venv + dépendances
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configurer l'environnement
cp .env.example .env
nano .env   # Remplir les clés
```

### Service systemd (auto-démarrage)

```ini
# /etc/systemd/system/agent-tel.service
[Unit]
Description=Agent Téléphonique IA
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/agent-tel
EnvironmentFile=/opt/agent-tel/.env
ExecStart=/opt/agent-tel/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-tel
sudo systemctl start agent-tel
sudo systemctl status agent-tel
```

### Nginx + TLS (obligatoire pour Twilio WebSocket)

Twilio exige `wss://` — un certificat TLS valide est obligatoire en production.

```bash
sudo apt install nginx certbot python3-certbot-nginx -y
sudo certbot --nginx -d votre-domaine.com
```

```nginx
# /etc/nginx/sites-available/agent-tel
server {
    listen 443 ssl;
    server_name votre-domaine.com;

    ssl_certificate /etc/letsencrypt/live/votre-domaine.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/votre-domaine.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600;   # WebSockets longue durée
    }
}
```

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## 5. Variables d'environnement de production

Utiliser un secrets manager plutôt qu'un fichier `.env` sur le serveur :

| Plateforme | Outil recommandé |
|---|---|
| Railway | Variables natives dans le dashboard |
| AWS | AWS Secrets Manager ou Parameter Store |
| GCP | Secret Manager |
| Indépendant | Doppler |

Sur Railway, les variables sont injectées automatiquement. Sur VPS, utiliser :
```bash
# Doppler
doppler run -- uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

## 6. Checklist mise en production

### Obligatoire

- [ ] `PUBLIC_URL` pointe vers le domaine de production en HTTPS
- [ ] Certificat TLS valide (requis pour `wss://`)
- [ ] `ffmpeg` installé sur le système hôte
- [ ] `DATABASE_URL` configuré (PostgreSQL recommandé en prod)
- [ ] Validation signature Twilio active (auto si `TWILIO_AUTH_TOKEN` configuré)
- [ ] Webhook Twilio configuré avec l'URL de production

### Recommandé

- [ ] Modèle Whisper adapté : `small` ou `medium` en prod
- [ ] Variables d'environnement dans un secrets manager
- [ ] `SENTRY_DSN` configuré pour le monitoring d'erreurs
- [ ] `SLACK_WEBHOOK_URL` configuré pour les notifications post-appel
- [ ] `ESCALATION_PHONE` configuré si transfert vers conseiller activé
- [ ] Logs centralisés (Papertrail / Datadog / CloudWatch)
- [ ] Redémarrage automatique configuré (systemd / Railway)

### Tests

- [ ] Test d'un appel entrant réel depuis un téléphone
- [ ] Test d'un appel sortant via `POST /calls/outbound`
- [ ] Test de la barge-in (interrompre l'agent pendant qu'il parle)
- [ ] Test du timeout (ne rien dire pendant `CALL_TIMEOUT_SECS` secondes)
- [ ] Vérifier `GET /admin/metrics` après quelques appels
- [ ] `_MOCK_CRM` remplacé par un vrai CRM

---

## 7. Commandes de maintenance

```bash
# Logs en temps réel (systemd)
sudo journalctl -u agent-tel -f

# Redémarrer
sudo systemctl restart agent-tel

# Mettre à jour le code
git pull origin main && sudo systemctl restart agent-tel

# Statut et ressources
sudo systemctl status agent-tel

# Railway : voir les logs
railway logs

# Railway : redéployer
railway up
```

---

## 8. Troubleshooting

| Problème | Cause probable | Solution |
|---|---|---|
| `WebSocket connection failed` | URL sans HTTPS ou mauvais port | Vérifier `PUBLIC_URL` et Nginx |
| `403 Signature Twilio invalide` | `TWILIO_AUTH_TOKEN` incorrect ou webhook mal configuré | Vérifier le token et l'URL exacte dans Twilio |
| `No audio heard on call` | ffmpeg manquant ou mauvais codec | Vérifier `ffmpeg --version` sur le serveur |
| `Whisper returns empty string` | Audio trop court / silence | Calibrer `SILENCE_THRESHOLD` |
| `Twilio 11200 error` | Webhook inaccessible | Vérifier ngrok / Nginx / URL publique |
| `openrouter 401` | Clé API invalide ou quota dépassé | Vérifier `OPENROUTER_API_KEY` sur openrouter.ai |
| `audioop` import error | Python 3.13+ | Installer `audioop-lts` et l'ajouter à `requirements.txt` |
| Voix TTS trop lente | edge-tts latence réseau Microsoft | Activer ElevenLabs ou `TTS_SENTENCE_STREAMING=true` |
| Whisper lent | Modèle trop grand | Réduire `WHISPER_MODEL` à `tiny` ou `base` |
| `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'` | FastAPI < 0.116 + Starlette 1.0 | `pip install "fastapi>=0.116"` |
| Agent ne répond plus (timeout) | Tâche agent bloquée | Vérifier `CALL_TIMEOUT_SECS`, inspecter les logs `stream_error` |
| Escalade ne transfère pas | `ESCALATION_PHONE` non configuré | Ajouter un numéro E.164 dans `.env` |
