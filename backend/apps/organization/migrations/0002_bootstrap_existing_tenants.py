"""Estructura inicial (oficina central, catálogos, feriados) para empresas existentes."""

from datetime import date

from django.db import migrations

from apps.organization import panama


def bootstrap(apps, schema_editor):
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    Tenant = apps.get_model("tenants", "Tenant")
    CostCenter = apps.get_model("organization", "CostCenter")
    CBACategory = apps.get_model("organization", "CBACategory")
    Position = apps.get_model("organization", "Position")
    Holiday = apps.get_model("organization", "Holiday")
    year = date.today().year
    for tenant in Tenant.objects.all():
        CostCenter.objects.get_or_create(
            tenant=tenant, code="OC", defaults={"name": "Oficina central", "kind": "office"}
        )
        categories = {}
        for code, name in panama.CBA_CATEGORIES:
            categories[code], _ = CBACategory.objects.get_or_create(
                tenant=tenant, code=code, defaults={"name": name}
            )
        for code, name, area, cba in panama.POSITIONS:
            Position.objects.get_or_create(
                tenant=tenant,
                code=code,
                defaults={"name": name, "area": area, "cba_category": categories.get(cba or "")},
            )
        for y in (year, year + 1):
            for day, name, kind in panama.national_holidays(y):
                Holiday.objects.get_or_create(
                    tenant=tenant, date=day, defaults={"name": name, "kind": kind}
                )


class Migration(migrations.Migration):
    dependencies = [
        ("organization", "0001_initial"),
        ("tenants", "0004_tenant_applies_cba"),
    ]

    operations = [migrations.RunPython(bootstrap, migrations.RunPython.noop)]
