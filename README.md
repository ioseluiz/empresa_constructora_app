# Constructora SaaS

Plataforma SaaS para administrar empresas constructoras: planilla por proyecto conforme a la
legislación de Panamá, marcaciones, vacaciones y, en fases posteriores, contabilidad y operaciones.
El plan completo está en [`docs/PLAN.md`](docs/PLAN.md).

## Estructura

| Carpeta | Contenido |
|---------|-----------|
| `backend/` | API Django 5.2 + DRF, Celery, PostgreSQL (gestionado con `uv`) |
| `frontend/` | React 19 + TypeScript + Vite + Tailwind CSS v4 |
| `.github/workflows/` | CI de backend y frontend |
| `docs/` | Plan maestro y documentación |

## Desarrollo local

### Opción A — Docker (todo el stack)

```bash
docker compose up --build
```

- Frontend: http://localhost:5173
- API: http://localhost:8000/api/v1/health/
- Documentación de la API (Swagger): http://localhost:8000/api/v1/docs/
- Postgres y Redis se exponen en los puertos 5433 y 6380 (configurables con
  `POSTGRES_HOST_PORT` y `REDIS_HOST_PORT`) para no chocar con instalaciones locales.

### Opción B — Sin Docker

Requiere Python 3.12, [uv](https://docs.astral.sh/uv/), Node 22 y PostgreSQL local.

```bash
# Backend
cd backend
cp .env.example .env             # ajustar DATABASE_URL
createdb constructora
uv sync
uv run python manage.py migrate
uv run python manage.py runserver

# Frontend (otra terminal)
cd frontend
npm install
npm run dev
```

## Calidad

```bash
make lint   # ruff + mypy + oxlint + prettier + tsc
make test   # pytest + vitest
```

Instalar los hooks de git: `cd backend && uv run pre-commit install` (desde la raíz del repo).

## Convenciones

- Montos siempre en `Decimal` (`apps.core.models.MoneyField`, `apps.core.money.round_money`), nunca `float`.
- Toda entidad de negocio hereda de `apps.core.models.BaseModel` (UUID + auditoría).
- Zona horaria `America/Panama`, idioma `es`.
