"""Vacaciones (Código de Trabajo de Panamá, arts. 54-60; validar con asesoría laboral).

- Se ganan 30 días por cada 11 meses de trabajo: aquí, 1 día por cada 11 días de relación
  laboral. El saldo se calcula siempre (no se guarda) a partir de la fecha de ingreso, las
  vacaciones aprobadas y los ajustes (p. ej. el saldo inicial al empezar a usar el sistema).
- Una solicitud aprobada se paga en la planilla regular o en una planilla de vacaciones.
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import MoneyField, TenantAwareModel


class VacationRequest(TenantAwareModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitada"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        CANCELLED = "cancelled", "Cancelada"

    class PaymentMode(models.TextChoices):
        PAYROLL = "payroll", "En la planilla regular"
        SEPARATE = "separate", "En planilla de vacaciones"

    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="vacations"
    )
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta")
    days = models.PositiveSmallIntegerField("días")
    payment_mode = models.CharField(
        "forma de pago", max_length=10, choices=PaymentMode.choices, default=PaymentMode.PAYROLL
    )
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.REQUESTED
    )
    notes = models.CharField("observaciones", max_length=255, blank=True)
    decided_at = models.DateTimeField("decidida", null=True, blank=True)
    decided_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reject_reason = models.CharField("motivo del rechazo", max_length=255, blank=True)
    paid_line = models.ForeignKey(
        "payroll.PayrollLine",
        verbose_name="pagada en",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vacations",
    )
    paid_amount = MoneyField("monto pagado", null=True, blank=True, default=None)

    class Meta:
        verbose_name = "vacaciones"
        verbose_name_plural = "vacaciones"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=models.F("start_date")), name="vacation_dates_consistent"
            ),
            models.CheckConstraint(condition=Q(days__gt=0), name="vacation_days_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.start_date}–{self.end_date}"

    @property
    def is_paid(self) -> bool:
        return self.paid_line_id is not None


class VacationAdjustment(TenantAwareModel):
    """Ajuste manual del saldo (positivo o negativo), p. ej. el saldo al migrar al sistema o
    vacaciones pagadas fuera de él."""

    employee = models.ForeignKey(
        "hr.Employee",
        verbose_name="empleado",
        on_delete=models.PROTECT,
        related_name="vacation_adjustments",
    )
    date = models.DateField("fecha")
    days = models.DecimalField("días", max_digits=6, decimal_places=2)
    reason = models.CharField("motivo", max_length=255)

    class Meta:
        verbose_name = "ajuste de vacaciones"
        verbose_name_plural = "ajustes de vacaciones"
        ordering = ["-date"]
        constraints = [
            models.CheckConstraint(condition=~Q(days=Decimal("0")), name="adjustment_not_zero"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.days} días"
