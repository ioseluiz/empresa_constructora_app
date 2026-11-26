"""Conceptos y parámetros de vacaciones y décimo tercer mes."""

from decimal import Decimal

from django.db import migrations

from apps.payroll_pa.parameters import FROM, PARAMETERS, VALIDATE
from apps.payroll_pa.rules import CONCEPTS

NEW_CONCEPTS = {"VACACIONES", "DECIMO", "CSS_DECIMO", "CSS_DECIMO_PATRONAL"}
NEW_PARAMS = {"vacation_pay_higher_of_current", "vacation_average_months", "decimo_divisor"}


def forwards(apps, schema_editor):
    schema_editor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
    LegalParameter = apps.get_model("payroll", "LegalParameter")
    for p in PARAMETERS:
        if p["key"] not in NEW_PARAMS:
            continue
        LegalParameter.objects.get_or_create(
            country="PA",
            key=p["key"],
            valid_from=FROM,
            defaults={
                "name": p["name"],
                "value": Decimal(p["value"]),
                "legal_basis": p.get("legal_basis", ""),
                "notes": VALIDATE,
            },
        )
    Tenant = apps.get_model("tenants", "Tenant")
    Concept = apps.get_model("payroll", "PayrollConcept")
    for tenant in Tenant.objects.all():
        for code, name, kind, css, se, isr, priority, legal in CONCEPTS:
            if code in NEW_CONCEPTS:
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
    dependencies = [("payroll_pa", "0001_seed_panama"), ("payroll", "0004_run_types")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
