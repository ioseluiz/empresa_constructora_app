"""Row-Level Security de PostgreSQL para tablas con `tenant_id`.

Cada migración que crea un modelo que hereda de `TenantAwareModel` debe incluir
`EnableTenantRLS("<modelo>")`. La prueba `test_all_tenant_tables_have_rls` falla
si alguno se olvida.

IMPORTANTE (producción): la aplicación debe conectarse con un rol que NO sea superusuario
ni tenga BYPASSRLS; de lo contrario PostgreSQL ignora estas políticas.
"""

from typing import Any

from django.db import migrations

from .tenancy import BYPASS_SETTING, TENANT_SETTING

POLICY_NAME = "tenant_isolation"

_CONDITION = (
    f"current_setting('{BYPASS_SETTING}', true) = 'on' "
    f"OR tenant_id = NULLIF(current_setting('{TENANT_SETTING}', true), '')::uuid"
)


def enable_rls_sql(table: str) -> list[str]:
    return [
        f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY',
        f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY',
        f'CREATE POLICY {POLICY_NAME} ON "{table}" USING ({_CONDITION}) WITH CHECK ({_CONDITION})',
    ]


def disable_rls_sql(table: str) -> list[str]:
    return [
        f'DROP POLICY IF EXISTS {POLICY_NAME} ON "{table}"',
        f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
        f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
    ]


class EnableTenantRLS(migrations.operations.base.Operation):
    reversible = True
    reduces_to_sql = True

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def state_forwards(self, app_label: str, state: Any) -> None:
        pass

    def _table(self, app_label: str, state: Any) -> str:
        return state.apps.get_model(app_label, self.model_name)._meta.db_table

    def database_forwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        for sql in enable_rls_sql(self._table(app_label, to_state)):
            schema_editor.execute(sql)

    def database_backwards(
        self, app_label: str, schema_editor: Any, from_state: Any, to_state: Any
    ) -> None:
        for sql in disable_rls_sql(self._table(app_label, from_state)):
            schema_editor.execute(sql)

    def describe(self) -> str:
        return f"Habilitar Row-Level Security por tenant en {self.model_name}"

    def deconstruct(self) -> tuple[str, list, dict]:
        return (self.__class__.__qualname__, [self.model_name], {})
