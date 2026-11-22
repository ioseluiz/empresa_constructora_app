.PHONY: up down demo backend-test frontend-test lint test

# Credenciales SOLO para desarrollo local.
DEMO_EMAIL ?= demo@constructora.pa
DEMO_PASSWORD ?= Demo-Obra-2026!

up:            ## Levanta todo el entorno local con Docker
	docker compose up --build

down:
	docker compose down

demo:         ## Crea dos empresas de prueba con el mismo usuario administrador
	docker compose exec backend python manage.py create_tenant --name "Constructora Istmo" --ruc 155-123-2026 --dv 45 --owner-email $(DEMO_EMAIL) --owner-password '$(DEMO_PASSWORD)'
	docker compose exec backend python manage.py create_tenant --name "Obras del Pacífico" --owner-email $(DEMO_EMAIL)

backend-test:
	cd backend && uv run pytest

frontend-test:
	cd frontend && npm test

lint:
	cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy .
	cd frontend && npm run lint && npm run format:check && npm run typecheck

test: backend-test frontend-test
