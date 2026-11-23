"""Parámetros legales de referencia de Panamá y conceptos/configuración para las empresas
existentes (las nuevas los reciben al crearse)."""

from decimal import Decimal

from django.db import migrations

from apps.payroll_pa.parameters import FROM, PARAMETERS, VALIDATE
from apps.payroll_pa.rules import CONCEPTS


def forwards(apps, schema_editor):
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    LegalParameter = apps.get_model("payroll", "LegalParameter")
    for p in PARAMETERS:
        LegalParameter.objects.get_or_create(
            country="PA",
            key=p["key"],
            valid_from=FROM,
            defaults={
                "name": p["name"],
                "value": Decimal(p["value"]) if "value" in p else None,
                "table": p.get("table"),
                "legal_basis": p.get("legal_basis", ""),
                "notes": " ".join(filter(None, [p.get("notes", ""), VALIDATE])),
            },
        )
    Tenant = apps.get_model("tenants", "Tenant")
    Settings = apps.get_model("payroll", "PayrollSettings")
    Concept = apps.get_model("payroll", "PayrollConcept")
    for tenant in Tenant.objects.all():
        Settings.objects.get_or_create(tenant=tenant, defaults={"country": "PA"})
        for code, name, kind, css, se, isr, priority, legal in CONCEPTS:
            Concept.objects.get_or_create(
                tenant=tenant,
                code=code,
                defaults={
                    "name": name,
                    "kind": kind,
                    "taxable_css": css,
                    "taxable_se": se,
                    "taxable_isr": isr,
                    "priority": priority,
                    "is_legal_order": legal,
                    "is_system": True,
                },
            )


class Migration(migrations.Migration):
    dependencies = [("payroll", "0001_initial"), ("tenants", "0004_tenant_applies_cba")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
