"""Pruebas del aislamiento entre empresas: manager (capa de aplicación) y RLS (base de datos).

Se usa un modelo de prueba creado al vuelo para no depender de módulos de negocio.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection, models

from apps.core.models import TenantAwareModel
from apps.core.rls import enable_rls_sql
from apps.core.tenancy import (
    TenantContextMissing,
    activate_tenant,
    bypass_tenant_scope,
    deactivate_tenant,
    tenant_context,
)

APP_ROLE = "constructora_rls_test"


class Obra(TenantAwareModel):
    nombre = models.CharField(max_length=50)

    class Meta:
        app_label = "core"
        db_table = "core_test_obra"


@pytest.fixture
def obra_table(db):
    with connection.schema_editor() as editor:
        editor.create_model(Obra)
    with connection.cursor() as cursor:
        for sql in enable_rls_sql(Obra._meta.db_table):
            cursor.execute(sql)
        cursor.execute(
            f"DO $$ BEGIN CREATE ROLE {APP_ROLE} NOLOGIN; "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$"
        )
        cursor.execute(f"GRANT SELECT, INSERT ON core_test_obra TO {APP_ROLE}")
    yield
    deactivate_tenant()


@pytest.fixture
def obras(obra_table, tenant, other_tenant):
    with tenant_context(tenant):
        Obra.objects.create(nombre="Torre Istmo")
    with tenant_context(other_tenant):
        Obra.objects.create(nombre="Puente Pacífico")


class TestManager:
    def test_without_context_fails_loudly(self, obras):
        with pytest.raises(TenantContextMissing):
            list(Obra.objects.all())

    def test_filters_by_active_tenant(self, obras, tenant, other_tenant):
        with tenant_context(tenant):
            assert [o.nombre for o in Obra.objects.all()] == ["Torre Istmo"]
        with tenant_context(other_tenant):
            assert [o.nombre for o in Obra.objects.all()] == ["Puente Pacífico"]

    def test_save_assigns_tenant(self, obra_table, tenant):
        with tenant_context(tenant):
            obra = Obra.objects.create(nombre="Edificio")
        assert obra.tenant_id == tenant.pk

    def test_cannot_save_into_other_tenant(self, obra_table, tenant, other_tenant):
        with tenant_context(tenant), pytest.raises(ValidationError):
            Obra(tenant=other_tenant, nombre="Intruso").save()

    def test_bypass_sees_all(self, obras):
        with bypass_tenant_scope():
            assert Obra.objects.count() == 2


class TestRowLevelSecurity:
    """Simula la conexión de la aplicación con un rol sin privilegios (como en producción):
    aunque el query no filtre, PostgreSQL solo devuelve filas del tenant activo."""

    def _raw_names(self) -> list[str]:
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL ROLE {APP_ROLE}")
            cursor.execute("SELECT nombre FROM core_test_obra ORDER BY nombre")
            rows = [r[0] for r in cursor.fetchall()]
            cursor.execute("RESET ROLE")
        return rows

    def test_no_tenant_sees_nothing(self, obras):
        assert self._raw_names() == []

    def test_sees_only_active_tenant(self, obras, tenant):
        activate_tenant(tenant)
        assert self._raw_names() == ["Torre Istmo"]

    def test_bypass_setting(self, obras):
        with bypass_tenant_scope():
            assert len(self._raw_names()) == 2

    def test_insert_into_other_tenant_blocked(self, obras, tenant, other_tenant):
        activate_tenant(tenant)
        with connection.cursor() as cursor:
            cursor.execute("SAVEPOINT rls")
            cursor.execute(f"SET LOCAL ROLE {APP_ROLE}")
            with pytest.raises(Exception, match="row-level security"):
                cursor.execute(
                    "INSERT INTO core_test_obra (id, tenant_id, nombre, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), %s, 'x', now(), now())",
                    [str(other_tenant.pk)],
                )
            cursor.execute("ROLLBACK TO SAVEPOINT rls")


# Tablas con columna tenant que NO llevan RLS a propósito (se consultan antes de conocer
# la empresa activa: login y selector de empresa).
RLS_EXEMPT = {"tenants_membership"}


@pytest.mark.django_db
def test_all_tenant_tables_have_rls():
    """Barrera contra olvidos: toda tabla con FK a la empresa debe tener RLS forzado."""
    tables = {
        m._meta.db_table
        for m in apps.get_models()
        if m is not Obra
        and not m._meta.proxy
        and any(
            f.name == "tenant" and getattr(f.related_model, "__name__", "") == "Tenant"
            for f in m._meta.get_fields()
            if f.concrete
        )
    } - RLS_EXEMPT
    assert "iam_role" in tables and "audit_auditlog" in tables
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relname = ANY(%s) "
            "AND relrowsecurity AND relforcerowsecurity",
            [list(tables)],
        )
        protected = {r[0] for r in cursor.fetchall()}
    assert tables == protected, f"Tablas sin RLS: {tables - protected}"


def test_nested_context_restores_db_setting(obras, tenant, other_tenant):
    def db_tenant() -> str:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.tenant_id', true)")
            return cursor.fetchone()[0]

    with tenant_context(tenant):
        with tenant_context(other_tenant):
            assert db_tenant() == str(other_tenant.pk)
        assert db_tenant() == str(tenant.pk)
    assert db_tenant() == ""
