from typing import Any

from .models import PayrollConcept, PayrollSettings
from .rules import rules_for


def bootstrap_payroll(country: str = "PA") -> PayrollSettings:
    """Configuración y conceptos del país para la empresa activa (no toca los existentes)."""
    settings, _ = PayrollSettings.objects.get_or_create(defaults={"country": country})
    for data in rules_for(settings.country).concepts():
        PayrollConcept.objects.get_or_create(
            code=data["code"], defaults={**data, "is_system": True}
        )
    return settings


def settings_for_tenant() -> Any:
    return PayrollSettings.objects.first() or bootstrap_payroll()
