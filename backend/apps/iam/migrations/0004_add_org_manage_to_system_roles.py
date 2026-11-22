"""Agrega el permiso nuevo `org.manage` a los roles plantilla existentes."""

from django.db import migrations

NEW_PERMISSION = "org.manage"
ROLES = ("Administrador", "Recursos humanos", "Contador")


def forwards(apps, schema_editor):
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    Role = apps.get_model("iam", "Role")
    for role in Role.objects.filter(is_system=True, name__in=ROLES):
        if NEW_PERMISSION not in role.permissions:
            role.permissions = sorted([*role.permissions, NEW_PERMISSION])
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("iam", "0003_roleassignment_projects")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
