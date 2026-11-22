from django.db import transaction

from apps.core.tenancy import tenant_context
from apps.tenants.models import Tenant

from . import panama
from .models import CBACategory, CostCenter, Holiday, Position

HEAD_OFFICE_CODE = "OC"


def generate_holidays(year: int) -> list[Holiday]:
    """Crea los feriados nacionales del año (no toca los existentes). Requiere tenant activo."""
    created = []
    for day, name, kind in panama.national_holidays(year):
        holiday, was_created = Holiday.objects.get_or_create(
            date=day, defaults={"name": name, "kind": kind}
        )
        if was_created:
            created.append(holiday)
    return created


@transaction.atomic
def bootstrap_organization(tenant: Tenant, years: tuple[int, ...]) -> None:
    """Estructura inicial de una empresa nueva: oficina central, catálogos y feriados."""
    with tenant_context(tenant):
        CostCenter.objects.get_or_create(
            code=HEAD_OFFICE_CODE,
            defaults={"name": "Oficina central", "kind": CostCenter.Kind.OFFICE},
        )
        categories = {}
        for code, name in panama.CBA_CATEGORIES:
            categories[code], _ = CBACategory.objects.get_or_create(
                code=code, defaults={"name": name}
            )
        for code, name, area, cba in panama.POSITIONS:
            Position.objects.get_or_create(
                code=code,
                defaults={"name": name, "area": area, "cba_category": categories.get(cba or "")},
            )
        for year in years:
            generate_holidays(year)
