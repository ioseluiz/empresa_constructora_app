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
from django.db import models


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
    """Base para entidades de negocio. En el Sprint 2 se agrega `tenant`."""

    class Meta:
        abstract = True


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
