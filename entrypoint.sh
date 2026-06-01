#!/bin/sh
set -e

# Appliquer les migrations au démarrage
alembic upgrade head

# Lancer l'application — $PORT défini par la plateforme (Railway, Cloud Run) ou 8000
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
