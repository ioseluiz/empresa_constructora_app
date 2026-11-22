"""Crea los roles plantilla en las empresas que ya existían antes del Sprint 3."""

from django.db import migrations

from apps.iam.catalog import DEFAULT_ROLES


def create_roles(apps, schema_editor):
    # Con FORCE ROW LEVEL SECURITY hasta el dueño de la tabla queda sujeto a RLS:
    # las migraciones de datos deben activar el modo plataforma explícitamente.
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    Tenant = apps.get_model("tenants", "Tenant")
    Role = apps.get_model("iam", "Role")
    for tenant in Tenant.objects.all():
        for name, spec in DEFAULT_ROLES.items():
            Role.objects.get_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    "description": spec["description"],
                    "permissions": spec["permissions"],
                    "is_system": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0001_initial"),
        ("tenants", "0002_tenant_require_mfa"),
    ]

    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
