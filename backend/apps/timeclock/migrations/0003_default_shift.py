"""Horario por defecto para las empresas existentes (las nuevas lo reciben al crearse)."""

from django.db import migrations


def forwards(apps, schema_editor):
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    Tenant = apps.get_model("tenants", "Tenant")
    Shift = apps.get_model("timeclock", "Shift")
    for tenant in Tenant.objects.all():
        if not Shift.objects.filter(tenant=tenant, is_default=True).exists():
            Shift.objects.get_or_create(
                tenant=tenant,
                code="DIU",
                defaults={
                    "name": "Diurno 7:00 a 16:00",
                    "start_time": "07:00",
                    "end_time": "16:00",
                    "break_minutes": 60,
                    "is_default": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [("timeclock", "0002_shifts_workdays"), ("tenants", "0004_tenant_applies_cba")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
