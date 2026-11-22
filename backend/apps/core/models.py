"""Modelos base abstractos que heredan todos los módulos de negocio.

Convenciones (ver docs/PLAN.md §3.4):
- PK UUID para no exponer conteos entre empresas.
- Marcas de auditoría en todos los registros.
- Montos con `MoneyField` (Decimal 18,2), nunca float.
"""

import uuid
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .tenancy import get_current_tenant, is_tenant_scope_bypassed, require_current_tenant


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        abstract = True


class AuditedModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="actualizado por",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        abstract = True


class BaseModel(UUIDModel, AuditedModel):
    """Base para entidades globales (no pertenecen a una empresa)."""

    class Meta:
        abstract = True


class TenantManager(models.Manager):
    """Manager por defecto de los modelos de empresa: siempre filtra por el tenant activo
    y falla en voz alta si no hay ninguno."""

    def get_queryset(self) -> models.QuerySet:
        qs = super().get_queryset()
        if is_tenant_scope_bypassed():
            return qs
        return qs.filter(tenant=require_current_tenant())


class TenantAwareModel(BaseModel):
    """Base para TODA entidad de negocio de una empresa (empleados, planillas, marcaciones…).

    La migración que crea el modelo debe incluir `apps.core.rls.EnableTenantRLS`.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant",
        verbose_name="empresa",
        on_delete=models.PROTECT,
        related_name="+",
        editable=False,
    )

    tenant_id: Any

    objects = TenantManager()
    all_tenants = models.Manager()  # noqa: DJ012 — solo para procesos de plataforma

    class Meta:
        abstract = True
        base_manager_name = "all_tenants"

    def save(self, *args: Any, **kwargs: Any) -> None:
        current = get_current_tenant()
        if self.tenant_id is None:
            self.tenant = require_current_tenant()
        elif current is not None and self.tenant_id != current.pk:
            raise ValidationError("No se puede guardar un registro de otra empresa.")
        super().save(*args, **kwargs)


class MoneyField(models.DecimalField):
    """Monto monetario: Decimal(18,2)."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 18)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("default", Decimal("0.00"))
        super().__init__(*args, **kwargs)


class RateField(models.DecimalField):
    """Tasa o porcentaje expresado como fracción: Decimal(9,6). Ej. 9.75% = 0.097500."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 6)
        super().__init__(*args, **kwargs)
