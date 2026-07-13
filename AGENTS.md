# Repository Guidelines

## Project Structure & Module Organization

This repository contains a FastAPI backend and a Vue/TypeScript frontend. Backend code lives in `src/app`: `api/routes` for endpoints, `services` for business logic, `repositories` for data access, `models` and `schemas` for persistence and API shapes, `rag` for retrieval workflows, `agents` and `tools` for copilot behavior, and `integrations` for external systems. Tests live in `tests`. SQL setup scripts are in `docs/sql`. Frontend code is under `frontend/src`, reusable packages under `frontend/packages`, static assets under `frontend/public`, and images/icons under `frontend/src/assets`.

## Build, Test, and Development Commands

- `python -m pip install -e ".[dev]"`: install backend dependencies plus pytest, ruff, and mypy.
- `uvicorn app.main:app --reload --app-dir src`: run the FastAPI app locally.
- `pytest`: run the backend test suite from `tests`.
- `ruff check src tests`: lint Python code using the repository's Ruff settings.
- `mypy src`: type-check backend modules.

The frontend has package manifests under `frontend/packages` but no root `frontend/package.json`; confirm the package manager before adding workspace commands.

## Coding Style & Naming Conventions

Python targets 3.12 with a 100-character line length. Use 4-space indentation, type hints for public functions, `snake_case` for modules/functions, and `PascalCase` for classes and Pydantic models. Keep route handlers thin; place reusable behavior in `services`, persistence in `repositories`, and external calls in `integrations`. Frontend files follow `frontend/.editorconfig`: UTF-8, LF endings, 2-space indentation, trimmed trailing whitespace, and a final newline.

## Testing Guidelines

Use pytest for backend tests. Name files `test_*.py` and functions `test_*`. Prefer focused tests beside the behavior they validate, such as route health checks in `tests/test_health.py`. Add async tests with `pytest-asyncio` when calling async code. Run `pytest` before submitting backend changes, and pair behavior changes with regression coverage.

## Commit & Pull Request Guidelines

This repository has no committed history yet, so use clear Conventional Commit-style subjects such as `feat: add document upload route` or `fix: handle empty retrieval results`. Pull requests should include a short summary, test results, linked issues when available, and screenshots or screen recordings for frontend UI changes. Call out migrations, new environment variables, and operational dependencies explicitly.

## Security & Configuration Tips

Keep secrets in `.env` and update `.env.example` when configuration changes. Do not commit credentials, API keys, database URLs, Redis passwords, MinIO secrets, or provider tokens. Treat SQL files in `docs/sql` as schema references and review them carefully before applying to shared environments.
