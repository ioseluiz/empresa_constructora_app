.PHONY: up down backend-test frontend-test lint test

up:            ## Levanta todo el entorno local con Docker
	docker compose up --build

down:
	docker compose down

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy .
	cd frontend && npm run lint && npm run format:check && npm run typecheck

test: backend-test frontend-test
