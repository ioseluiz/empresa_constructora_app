from django.contrib import admin

from apps.iam.admin import AllTenantsAdmin

from .models import CBACategory, CBAWageRate, CostCenter, Holiday, Position

for model, fields in [
    (CostCenter, ["code", "name", "kind", "tenant", "is_active"]),
    (Position, ["code", "name", "area", "tenant"]),
    (CBACategory, ["code", "name", "tenant"]),
    (CBAWageRate, ["category", "hourly_rate", "valid_from", "tenant"]),
    (Holiday, ["date", "name", "kind", "tenant"]),
]:
    admin.site.register(
        model, type(f"{model.__name__}Admin", (AllTenantsAdmin,), {"list_display": fields})
    )
