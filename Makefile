.PHONY: up down demo schema backend-test frontend-test lint test

# Credenciales SOLO para desarrollo local.
DEMO_EMAIL ?= demo@constructora.pa
DEMO_PASSWORD ?= Demo-Obra-2026!

up:            ## Levanta todo el entorno local con Docker
	docker compose up --build --renew-anon-volumes

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
	cd backend && uv run python manage.py makemigrations --check --dry-run
	cd frontend && npm run lint && npm run format:check && npm run typecheck

test: backend-test frontend-test

schema:        ## Exporta el esquema OpenAPI y regenera el cliente del frontend
	cd backend && uv run python manage.py spectacular --format openapi-json --file ../frontend/openapi.json
	cd frontend && npm run api:generate
