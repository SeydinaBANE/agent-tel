VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
PYTEST = $(VENV)/bin/pytest
UVICORN = $(VENV)/bin/uvicorn

.PHONY: help install run dev test test-unit test-cov lint format typecheck clean ngrok hooks

help:
	@echo ""
	@echo "  Agent Téléphonique IA"
	@echo ""
	@echo "  make install      Installe les dépendances"
	@echo "  make run          Lance le serveur (prod)"
	@echo "  make dev          Lance le serveur avec reload"
	@echo "  make test         Lance tous les tests"
	@echo "  make test-unit    Lance les tests sans coverage"
	@echo "  make test-cov     Lance les tests + rapport HTML"
	@echo "  make lint         Vérifie le code (ruff)"
	@echo "  make format       Formate le code (ruff format)"
	@echo "  make typecheck    Vérifie les types (mypy)"
	@echo "  make hooks        Installe les pre-commit hooks"
	@echo "  make ngrok        Ouvre un tunnel ngrok sur le port 8000"
	@echo "  make clean        Supprime les fichiers temporaires"
	@echo ""

install:
	$(PIP) install -r requirements.txt

run:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000

dev:
	$(UVICORN) app.main:app --host 0.0.0.0 --port 8000 --reload

test:
	$(PYTEST) tests/ -v

test-unit:
	$(PYTEST) tests/ -v --no-cov

test-cov:
	$(PYTEST) tests/ -v --cov=app --cov-report=html
	@echo "Rapport HTML : htmlcov/index.html"

lint:
	$(VENV)/bin/ruff check app/ tests/

format:
	$(VENV)/bin/ruff format app/ tests/
	$(VENV)/bin/ruff check --fix app/ tests/

typecheck:
	$(VENV)/bin/mypy app/ --ignore-missing-imports

hooks:
	$(VENV)/bin/pre-commit install
	@echo "Pre-commit hooks installés."

ngrok:
	ngrok http 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache htmlcov .coverage .mypy_cache
