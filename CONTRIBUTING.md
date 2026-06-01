# Contribuer

## Branches

- `main` — production, protégée. Pas de push direct.
- `feat/*` — nouvelles fonctionnalités.
- `fix/*` — corrections de bugs.

## Workflow

1. Créer une branche depuis `main`
2. Coder les changements
3. `make lint && make format && make typecheck && make test` — tout doit passer
4. Créer une Pull Request vers `main`
5. Un maintainer review et merge

## Conventions de code

- Python 3.11+ avec type hints stricts (tous les paramètres et retours)
- Tout I/O est `async`
- Pas de commentaires sauf WHY non-évident
- Tools Agno : logique pure dans `_fn()`, décorateur Agno séparé
- `ruff` line-length = 100
- `mypy` avec `no_strict_optional = true`

## Tests

- `pytest` avec `asyncio_mode = auto`
- Ajouter au moins un test nominal + un test d'erreur pour chaque nouvelle fonction
- Mocker les agents Agno et Whisper (pas d'appels LLM réels)
- Les outils sont testés via leur fonction `_fn` (pure), pas le décorateur Agno

## Commit

Pas de format imposé. Essayez de décrire brièvement ce que fait le changement.
