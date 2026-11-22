"""Estructura de la empresa y catálogos compartidos por todos los módulos:
centros de costo, puestos, categorías y tarifas de la convención colectiva, feriados."""

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import TenantAwareModel


class CostCenter(TenantAwareModel):
    """Árbol de centros de costo. La oficina central y cada proyecto son centros de costo;
    la planilla y la contabilidad imputan cada monto a uno de ellos (docs/PLAN.md §4.2)."""

    class Kind(models.TextChoices):
        OFFICE = "office", "Oficina"
        PROJECT = "project", "Proyecto"
        AREA = "area", "Área / fase"

    code = models.CharField("código", max_length=30)
    name = models.CharField("nombre", max_length=150)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.AREA)
    parent = models.ForeignKey(
        "self",
        verbose_name="centro de costo padre",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "centro de costo"
        verbose_name_plural = "centros de costo"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_cost_center_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"

    def clean(self) -> None:
        node = self.parent
        while node is not None:
            if node.pk == self.pk:
                raise ValidationError(
                    {"parent": "Un centro de costo no puede ser su propio ancestro."}
                )
            node = node.parent


class CBACategory(TenantAwareModel):
    """Categoría ocupacional de la Convención Colectiva SUNTRACS–CAPAC."""

    code = models.CharField("código", max_length=20)
    name = models.CharField("nombre", max_length=120)
    description = models.CharField("descripción", max_length=255, blank=True)
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "categoría de convención"
        verbose_name_plural = "categorías de convención"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_cba_category_code"),
        ]

    def __str__(self) -> str:
        return self.name

    def rate_on(self, on: date) -> "CBAWageRate | None":
        return self.rates.filter(valid_from__lte=on).order_by("-valid_from").first()


class CBAWageRate(TenantAwareModel):
    """Tarifa por hora vigente desde una fecha (vigencia hasta la siguiente tarifa)."""

    category = models.ForeignKey(
        CBACategory, verbose_name="categoría", on_delete=models.CASCADE, related_name="rates"
    )
    hourly_rate = models.DecimalField("tarifa por hora", max_digits=10, decimal_places=4)
    valid_from = models.DateField("vigente desde")
    source = models.CharField(
        "fuente", max_length=255, blank=True, help_text="Ej. Convención 2026-2029, cláusula 12."
    )

    class Meta:
        verbose_name = "tarifa de convención"
        verbose_name_plural = "tarifas de convención"
        ordering = ["category", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "valid_from"], name="unique_cba_rate_per_date"
            ),
            models.CheckConstraint(
                condition=models.Q(hourly_rate__gt=Decimal("0")), name="cba_rate_positive"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.category} B/.{self.hourly_rate} desde {self.valid_from}"


class Position(TenantAwareModel):
    class Area(models.TextChoices):
        FIELD = "field", "Obra"
        OFFICE = "office", "Oficina"

    code = models.CharField("código", max_length=20)
    name = models.CharField("nombre", max_length=120)
    area = models.CharField("área", max_length=10, choices=Area.choices, default=Area.FIELD)
    cba_category = models.ForeignKey(
        CBACategory,
        verbose_name="categoría de convención",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="positions",
    )
    description = models.CharField("descripción", max_length=255, blank=True)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "puesto"
        verbose_name_plural = "puestos"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_position_code"),
        ]

    def __str__(self) -> str:
        return self.name


class Holiday(TenantAwareModel):
    """Feriado o día de duelo. Se usa para clasificar horas trabajadas (recargo de feriado)."""

    class Kind(models.TextChoices):
        NATIONAL = "national", "Fiesta nacional"
        MOURNING = "mourning", "Duelo nacional"
        DECREED = "decreed", "Decretado"
        COMPANY = "company", "De la empresa"

    date = models.DateField("fecha")
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices, default=Kind.NATIONAL)
    is_paid_rest = models.BooleanField(
        "descanso obligatorio remunerado",
        default=True,
        help_text="Si se trabaja, aplica el recargo de feriado.",
    )

    class Meta:
        verbose_name = "feriado"
        verbose_name_plural = "feriados"
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "date"], name="unique_holiday_date"),
        ]

    def __str__(self) -> str:
        return f"{self.date:%d/%m/%Y} {self.name}"
