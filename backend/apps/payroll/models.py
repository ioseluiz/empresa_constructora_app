"""Núcleo de planilla, independiente del país (docs/PLAN.md §4.1).

- `LegalParameter`: tasas, topes y tablas por país con vigencia por fecha. Es una tabla global
  de la plataforma (la ley es la misma para todas las empresas): cuando cambia una tasa se carga
  una vigencia nueva, sin desplegar código. Las empresas no la editan.
- `PayrollSettings`: valores propios de cada empresa (tasa de riesgos profesionales, etc.).
- `PayrollConcept`: catálogo de conceptos (ingresos, deducciones, aportes y provisiones) con su
  tratamiento fiscal y su cuenta contable (para la contabilidad de la fase 2).
- `RecurringDeduction`: descuentos del empleado (préstamos, pensión alimenticia, embargos…).
"""

from decimal import Decimal

from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, MoneyField, RateField, TenantAwareModel


class LegalParameter(BaseModel):
    country = models.CharField("país", max_length=2, default="PA")
    key = models.CharField("clave", max_length=60)
    name = models.CharField("nombre", max_length=150)
    value = models.DecimalField("valor", max_digits=14, decimal_places=6, null=True, blank=True)
    table = models.JSONField("tabla", null=True, blank=True, help_text="Para tablas por tramos.")
    valid_from = models.DateField("vigente desde")
    legal_basis = models.CharField("base legal", max_length=255, blank=True)
    notes = models.TextField("notas", blank=True)

    class Meta:
        verbose_name = "parámetro legal"
        verbose_name_plural = "parámetros legales"
        ordering = ["country", "key", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["country", "key", "valid_from"], name="unique_legal_parameter_version"
            ),
            models.CheckConstraint(
                condition=Q(value__isnull=False) | Q(table__isnull=False),
                name="legal_parameter_has_value",
            ),
        ]

    def __str__(self) -> str:
        shown = self.value if self.value is not None else "tabla"
        return f"{self.country}.{self.key} = {shown} desde {self.valid_from}"


class PayrollSettings(TenantAwareModel):
    """Configuración de planilla de la empresa (una por empresa)."""

    country = models.CharField("país de la legislación", max_length=2, default="PA")
    occupational_risk_rate = RateField(
        "tasa de riesgos profesionales",
        default=Decimal("0.0"),
        help_text="Aporte patronal según la actividad (la CSS la asigna a cada empresa). "
        "Ej.: 0.0567 = 5.67 %.",
    )
    union_dues_rate = RateField(
        "cuota sindical (% del salario bruto)",
        default=Decimal("0.0"),
        help_text="Se descuenta a los empleados afiliados al sindicato.",
    )
    deduct_unworked_time = models.BooleanField(
        "descontar tiempo no laborado a asalariados",
        default=True,
        help_text="Ausencias, tardanzas y salidas anticipadas de jornadas aprobadas.",
    )

    class Meta:
        verbose_name = "configuración de planilla"
        verbose_name_plural = "configuración de planilla"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], name="unique_payroll_settings"),
        ]

    def __str__(self) -> str:
        return f"Planilla {self.tenant_id}"


class PayrollConcept(TenantAwareModel):
    class Kind(models.TextChoices):
        EARNING = "earning", "Ingreso"
        DEDUCTION = "deduction", "Deducción"
        EMPLOYER = "employer", "Aporte patronal"
        PROVISION = "provision", "Provisión"

    code = models.CharField("código", max_length=30)
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=Kind.choices)
    taxable_css = models.BooleanField("cotiza al Seguro Social", default=False)
    taxable_se = models.BooleanField("cotiza al Seguro Educativo", default=False)
    taxable_isr = models.BooleanField("gravable para ISR", default=False)
    priority = models.PositiveSmallIntegerField(
        "prioridad",
        default=100,
        help_text="Orden de aplicación de las deducciones (menor primero).",
    )
    is_legal_order = models.BooleanField(
        "orden judicial",
        default=False,
        help_text="Pensión alimenticia o embargo: se descuenta aunque reduzca otros descuentos.",
    )
    is_system = models.BooleanField("del sistema", default=False, editable=False)
    accounting_account = models.CharField("cuenta contable", max_length=30, blank=True)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "concepto de planilla"
        verbose_name_plural = "conceptos de planilla"
        ordering = ["kind", "priority", "code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_payroll_concept_code"),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class RecurringDeduction(TenantAwareModel):
    """Descuento que se aplica en cada planilla del empleado mientras esté vigente. Si tiene
    monto total (préstamo), se detiene al completarlo."""

    employee = models.ForeignKey(
        "hr.Employee",
        verbose_name="empleado",
        on_delete=models.PROTECT,
        related_name="recurring_deductions",
    )
    concept = models.ForeignKey(
        PayrollConcept,
        verbose_name="concepto",
        on_delete=models.PROTECT,
        related_name="recurring_deductions",
        limit_choices_to={"kind": PayrollConcept.Kind.DEDUCTION},
    )
    amount_per_period = MoneyField("cuota por planilla")
    total_amount = MoneyField("monto total", null=True, blank=True, default=None)
    paid_amount = MoneyField("pagado", default=Decimal("0"))
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta", null=True, blank=True)
    creditor = models.CharField("acreedor / beneficiario", max_length=150, blank=True)
    reference = models.CharField("referencia (oficio, contrato…)", max_length=100, blank=True)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "descuento recurrente"
        verbose_name_plural = "descuentos recurrentes"
        ordering = ["employee", "concept__priority"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount_per_period__gt=Decimal("0")), name="deduction_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(total_amount__isnull=True) | Q(total_amount__gt=Decimal("0")),
                name="deduction_total_positive",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="deduction_dates_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.concept.name} {self.amount_per_period}"

    @property
    def balance(self) -> Decimal | None:
        if self.total_amount is None:
            return None
        return max(Decimal("0"), self.total_amount - self.paid_amount)
