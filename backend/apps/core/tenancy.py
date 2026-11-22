"""Contexto de empresa (tenant) activo y su propagación a PostgreSQL.

Dos barreras de aislamiento (docs/PLAN.md §2.2):
1. Aplicación: `TenantManager` filtra por el tenant activo y falla si no hay ninguno.
2. Base de datos: Row-Level Security lee `app.tenant_id`, que aquí se fija con
   `set_config(..., is_local => true)`, es decir, solo para la transacción en curso.
   Fuera de una transacción el valor se pierde de inmediato y RLS no devuelve filas:
   el modo de falla es "no ver nada", nunca "ver datos ajenos".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.db import connection, transaction

if TYPE_CHECKING:
    from apps.tenants.models import Tenant

_current_tenant: ContextVar[Tenant | None] = ContextVar("current_tenant", default=None)
_bypass: ContextVar[bool] = ContextVar("tenant_bypass", default=False)

TENANT_SETTING = "app.tenant_id"
BYPASS_SETTING = "app.bypass_rls"


class TenantContextMissing(RuntimeError):
    """Se intentó consultar datos de una empresa sin un tenant activo."""


def get_current_tenant() -> Tenant | None:
    return _current_tenant.get()


def require_current_tenant() -> Tenant:
    tenant = _current_tenant.get()
    if tenant is None:
        raise TenantContextMissing(
            "No hay empresa activa. Use una vista con alcance de tenant o `tenant_context()`."
        )
    return tenant


def is_tenant_scope_bypassed() -> bool:
    return _bypass.get()


def _set_db_setting(name: str, value: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, %s, true)", [name, value])


def activate_tenant(tenant: Tenant) -> None:
    """Activa el tenant para el resto de la petición. Requiere una transacción abierta
    (ATOMIC_REQUESTS la garantiza en las vistas)."""
    _current_tenant.set(tenant)
    _set_db_setting(TENANT_SETTING, str(tenant.pk))


def deactivate_tenant() -> None:
    _current_tenant.set(None)
    _bypass.set(False)


@contextmanager
def tenant_context(tenant: Tenant) -> Iterator[Tenant]:
    """Para tareas Celery, comandos y pruebas: ejecuta el bloque dentro de una transacción
    con el tenant activo."""
    previous = _current_tenant.get()
    token = _current_tenant.set(tenant)
    try:
        with transaction.atomic():
            _set_db_setting(TENANT_SETTING, str(tenant.pk))
            yield tenant
            # SET LOCAL dura hasta el fin de la transacción externa: si este bloque está
            # anidado se restaura el valor previo (ante una excepción lo revierte el rollback
            # del savepoint).
            _set_db_setting(TENANT_SETTING, str(previous.pk) if previous else "")
    finally:
        _current_tenant.reset(token)


@contextmanager
def bypass_tenant_scope() -> Iterator[None]:
    """Acceso entre empresas (procesos de plataforma, reportes globales del SaaS).
    Úselo solo en código de infraestructura, nunca en vistas de negocio."""
    previous = _bypass.get()
    token = _bypass.set(True)
    try:
        with transaction.atomic():
            _set_db_setting(BYPASS_SETTING, "on")
            yield
            _set_db_setting(BYPASS_SETTING, "on" if previous else "")
    finally:
        _bypass.reset(token)
