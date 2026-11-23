"""Horas aprobadas por proyecto: el único insumo de horas que usa la planilla (docs/PLAN.md §4.1).

Se generan al aprobar una jornada (`timeclock.WorkDay`) y se eliminan si la jornada se reabre,
mientras no hayan sido usadas en una planilla (`locked`).
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import TenantAwareModel


class TimeEntry(TenantAwareModel):
    class HourType(models.TextChoices):
        ORDINARY = "ordinary", "Ordinaria"
        OVERTIME_DAY = "ot_day", "Extra diurna"
        OVERTIME_NIGHT = "ot_night", "Extra nocturna"
        OVERTIME_MIXED = "ot_mixed", "Extra mixta (prolongación nocturna)"

    class DayKind(models.TextChoices):
        REGULAR = "regular", "Laborable"
        REST = "rest", "Descanso"
        HOLIDAY = "holiday", "Feriado"

    employee = models.ForeignKey(
        "hr.Employee",
        verbose_name="empleado",
        on_delete=models.PROTECT,
        related_name="time_entries",
    )
    date = models.DateField("fecha")
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="time_entries",
    )
    cost_center = models.ForeignKey(
        "organization.CostCenter",
        verbose_name="centro de costo",
        on_delete=models.PROTECT,
        related_name="time_entries",
    )
    hour_type = models.CharField("tipo de hora", max_length=10, choices=HourType.choices)
    day_kind = models.CharField("tipo de día", max_length=8, choices=DayKind.choices)
    jornada = models.CharField("jornada", max_length=5, blank=True)
    hours = models.DecimalField("horas", max_digits=5, decimal_places=2)
    workday = models.ForeignKey(
        "timeclock.WorkDay",
        verbose_name="jornada",
        on_delete=models.CASCADE,
        related_name="time_entries",
    )
    locked = models.BooleanField(
        "usada en planilla", default=False, help_text="Ya no se puede reabrir la jornada."
    )

    class Meta:
        verbose_name = "hora aprobada"
        verbose_name_plural = "horas aprobadas"
        ordering = ["date", "employee"]
        indexes = [models.Index(fields=["tenant", "date", "project"])]
        constraints = [
            models.UniqueConstraint(fields=["workday", "hour_type"], name="unique_entry_per_type"),
            models.CheckConstraint(condition=Q(hours__gt=Decimal("0")), name="time_entry_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.date} {self.hour_type} {self.hours}h"
