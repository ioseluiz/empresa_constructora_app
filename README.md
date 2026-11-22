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
- Datos de prueba: `make demo` crea dos empresas con un usuario administrador
  (credenciales de desarrollo en el `Makefile`).
- Los correos (recuperación de contraseña) se imprimen en los logs: `docker compose logs backend`.
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

## Multiempresa y autenticación

- Cada petición de negocio lleva `Authorization: Bearer <access>` y `X-Tenant-ID: <empresa>`.
- El refresh token rota en cada uso y viaja solo en una cookie httpOnly (`/api/v1/auth/`).
- Las vistas de negocio heredan de `apps.tenants.views.TenantScopedAPIView`.
- Los modelos de negocio heredan de `apps.core.models.TenantAwareModel` y su migración debe
  incluir `apps.core.rls.EnableTenantRLS("<Modelo>")` (una prueba lo verifica).
- En producción la app debe conectarse a Postgres con un rol **sin** superusuario ni
  `BYPASSRLS`; si no, PostgreSQL ignora las políticas de Row-Level Security.
- Alta de empresas: `python manage.py create_tenant --name ... --owner-email ...`.

## Convenciones

- Montos siempre en `Decimal` (`apps.core.models.MoneyField`, `apps.core.money.round_money`), nunca `float`.
- Toda entidad de negocio hereda de `apps.core.models.BaseModel` (UUID + auditoría).
- Zona horaria `America/Panama`, idioma `es`.
