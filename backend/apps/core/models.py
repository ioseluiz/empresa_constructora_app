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


class TenantQuerySet(models.QuerySet):
    """QuerySet que aplica el filtro de empresa al momento de ejecutarse.

    Si se construye sin empresa activa (p. ej. al importar módulos: django-filter y DRF
    crean querysets en tiempo de definición de clases), el filtro queda pendiente y se aplica
    con la empresa activa al evaluarlo. Si al evaluar sigue sin haber empresa, falla.
    """

    _tenant_pending = False

    def _clone(self) -> "TenantQuerySet":
        clone = super()._clone()  # type: ignore[misc]
        clone._tenant_pending = self._tenant_pending
        return clone

    def _apply_tenant_filter(self) -> None:
        if not self._tenant_pending:
            return
        if not is_tenant_scope_bypassed():
            self.query.add_q(models.Q(tenant=require_current_tenant()))
        self._tenant_pending = False

    def _fetch_all(self) -> None:
        self._apply_tenant_filter()
        super()._fetch_all()

    def iterator(self, *args: Any, **kwargs: Any) -> Any:
        self._apply_tenant_filter()
        return super().iterator(*args, **kwargs)

    def count(self) -> int:
        self._apply_tenant_filter()
        return super().count()

    def exists(self) -> bool:
        self._apply_tenant_filter()
        return super().exists()

    def aggregate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._apply_tenant_filter()
        return super().aggregate(*args, **kwargs)

    def update(self, **kwargs: Any) -> int:
        self._apply_tenant_filter()
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        self._apply_tenant_filter()
        return super().delete()


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):  # type: ignore[misc]
    """Manager por defecto de los modelos de empresa: siempre filtra por el tenant activo
    y falla en voz alta si se ejecuta una consulta sin ninguno."""

    def get_queryset(self) -> TenantQuerySet:
        qs: TenantQuerySet = super().get_queryset()
        if is_tenant_scope_bypassed():
            return qs
        tenant = get_current_tenant()
        if tenant is not None:
            return qs.filter(tenant=tenant)
        qs._tenant_pending = True
        return qs


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
