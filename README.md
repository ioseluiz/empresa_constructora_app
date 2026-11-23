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
- Alta de empresas: `python manage.py create_tenant --name ... --owner-email ...` (crea también
  los roles plantilla).
- Las migraciones **de datos** sobre tablas con RLS deben ejecutar
  `SELECT set_config('app.bypass_rls', 'on', true)` al inicio (ver `iam/0002`).

## Roles, permisos y auditoría

- El catálogo de permisos vive en `backend/apps/iam/catalog.py` (código `recurso.acción`). Cada
  módulo nuevo agrega ahí sus permisos y, si aplica, los suma a los roles plantilla.
- Las vistas de negocio usan `apps.iam.permissions.TenantPermissionMixin` y declaran
  `permission_resource`, `required_permission` o `action_permissions`.
- Los cambios relevantes se registran con `apps.audit.services.record(...)`. La bitácora es de
  solo inserción (un trigger de Postgres impide modificarla o borrarla).
- MFA (TOTP) por usuario; cada empresa puede exigirlo. Los secretos se cifran con
  `MFA_ENCRYPTION_KEY`.

## Organización y proyectos

- Cada empresa nueva arranca con: centro de costo "Oficina central", categorías de la convención
  SUNTRACS–CAPAC (sin tarifas: se cargan desde la convención vigente), puestos habituales y los
  feriados nacionales del año en curso y el siguiente (`apps/organization/panama.py`).
- Cada proyecto crea y mantiene sincronizado su propio centro de costo.
- Un rol asignado sin proyectos aplica a toda la empresa; con proyectos, solo a esas obras.
  Las vistas filtran con `apps.iam.permissions.filter_by_project_scope(...)`.
- Los permisos nuevos que se agreguen al catálogo requieren una migración de datos que los sume a
  los roles plantilla existentes (ver `iam/0004`).

## Empleados (`apps/hr`)

- Expediente: datos personales (cédula validada con el formato panameño), seguro social, forma de
  pago y cuenta bancaria. Los datos bancarios y salarios solo los ve quien tiene `hr.salary.view`.
- Contratos (indefinido, definido, obra determinada) con historial salarial por fecha de vigencia
  (`SalaryRecord`): un aumento es un registro nuevo, nunca se sobrescribe. La planilla usará
  `contract.salary_on(fecha)`. Con convención, la tarifa puede seguir la tabla vigente.
- PostgreSQL impide contratos solapados del mismo empleado y asignaciones solapadas al mismo
  proyecto (restricciones de exclusión con `btree_gist`).
- Un rol limitado a ciertos proyectos solo ve a los empleados asignados a esos proyectos.
- Los documentos se guardan con nombre aleatorio y solo se descargan por el endpoint autenticado
  (`/hr/documents/{id}/download/`), validando tipo y contenido (PDF/JPG/PNG, máx. 10 MB).

## Cliente de la API (orval)

El frontend usa tipos y hooks de TanStack Query generados desde el esquema OpenAPI:

```bash
make schema   # exporta frontend/openapi.json y regenera frontend/src/api/generated
```

La CI falla si el esquema o el cliente generado no están al día con el backend.

## Convenciones

- Montos siempre en `Decimal` (`apps.core.models.MoneyField`, `apps.core.money.round_money`), nunca `float`.
- Toda entidad de negocio hereda de `apps.core.models.BaseModel` (UUID + auditoría).
- Zona horaria `America/Panama`, idioma `es`.
