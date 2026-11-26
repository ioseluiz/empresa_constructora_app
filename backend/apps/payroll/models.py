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

from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel, MoneyField, RateField, TenantAwareModel
from apps.organization.panama import BANKS


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
    payslip_show_employer = models.BooleanField(
        "mostrar aportes patronales en el comprobante", default=False
    )
    company_bank = models.CharField("banco de la empresa", max_length=20, choices=BANKS, blank=True)
    company_account_type = models.CharField(
        "tipo de cuenta de la empresa",
        max_length=10,
        choices=[("savings", "Ahorros"), ("checking", "Corriente")],
        blank=True,
    )
    company_account_number = models.CharField("cuenta de la empresa", max_length=30, blank=True)
    ach_routes = models.JSONField(
        "códigos de ruta ACH por banco",
        default=dict,
        blank=True,
        help_text='Ej.: {"banco_general": "71"}. Los da el banco al habilitar el servicio ACH.',
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


class PayrollRun(TenantAwareModel):
    """Corrida de planilla de un período. Aprobada es inmutable: las correcciones se hacen con
    ajustes en un período siguiente."""

    class RunType(models.TextChoices):
        REGULAR = "regular", "Regular"
        DECIMO = "decimo", "Décimo tercer mes"
        VACATION = "vacation", "Vacaciones"

    class Scope(models.TextChoices):
        PROJECT = "project", "Proyecto"
        OFFICE = "office", "Oficina central"
        COMPANY = "company", "Toda la empresa"

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Semanal"
        BIWEEKLY = "biweekly", "Quincenal"
        MONTHLY = "monthly", "Mensual"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        CALCULATED = "calculated", "Calculada"
        APPROVED = "approved", "Aprobada"
        PAID = "paid", "Pagada"
        CANCELLED = "cancelled", "Anulada"

    number = models.PositiveIntegerField("número", editable=False)
    run_type = models.CharField(
        "tipo", max_length=12, choices=RunType.choices, default=RunType.REGULAR
    )
    frequency = models.CharField(
        "frecuencia",
        max_length=10,
        choices=Frequency.choices,
        blank=True,
        help_text="Solo planillas regulares: el décimo y las vacaciones incluyen a todos.",
    )
    scope = models.CharField("alcance", max_length=10, choices=Scope.choices)
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payroll_runs",
    )
    period_start = models.DateField("inicio del período")
    period_end = models.DateField("fin del período")
    pay_date = models.DateField("fecha de pago")
    status = models.CharField("estado", max_length=12, choices=Status.choices, default=Status.DRAFT)
    employee_count = models.PositiveIntegerField("empleados", default=0)
    gross = MoneyField("bruto", default=Decimal("0"))
    deductions = MoneyField("deducciones", default=Decimal("0"))
    net = MoneyField("neto", default=Decimal("0"))
    employer_contributions = MoneyField("aportes patronales", default=Decimal("0"))
    provisions = MoneyField("provisiones", default=Decimal("0"))
    parameters = models.JSONField("parámetros legales usados", default=dict, blank=True)
    notes = models.CharField("observaciones", max_length=255, blank=True)
    calculated_at = models.DateTimeField("calculada", null=True, blank=True)
    calculated_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    approved_at = models.DateTimeField("aprobada", null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    paid_at = models.DateTimeField("pagada", null=True, blank=True)
    paid_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = "corrida de planilla"
        verbose_name_plural = "corridas de planilla"
        ordering = ["-period_end", "-number"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_payroll_run_number"),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="payroll_run_dates_consistent",
            ),
            models.CheckConstraint(
                condition=~Q(scope="project") | Q(project__isnull=False),
                name="project_run_has_project",
            ),
        ]

    def __str__(self) -> str:
        return f"Planilla #{self.number} {self.period_start:%d/%m}–{self.period_end:%d/%m/%Y}"

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.CALCULATED)


class PayrollLine(TenantAwareModel):
    """Resultado de un empleado en una corrida."""

    run = models.ForeignKey(
        PayrollRun, verbose_name="corrida", on_delete=models.CASCADE, related_name="lines"
    )
    employee = models.ForeignKey(
        "hr.Employee",
        verbose_name="empleado",
        on_delete=models.PROTECT,
        related_name="payroll_lines",
    )
    contract = models.ForeignKey(
        "hr.EmploymentContract", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    pay_basis = models.CharField("base de pago", max_length=10, blank=True)
    gross = MoneyField("bruto", default=Decimal("0"))
    deductions = MoneyField("deducciones", default=Decimal("0"))
    net = MoneyField("neto", default=Decimal("0"))
    employer_contributions = MoneyField("aportes patronales", default=Decimal("0"))
    provisions = MoneyField("provisiones", default=Decimal("0"))
    warnings = models.JSONField("advertencias", default=list, blank=True)
    explanation = models.JSONField("explicación", default=list, blank=True)
    error = models.CharField("error", max_length=255, blank=True)
    vacation_payments = models.JSONField(
        "vacaciones pagadas", default=dict, blank=True, help_text="Solicitud → monto."
    )
    time_entry_ids = ArrayField(
        models.UUIDField(), verbose_name="horas incluidas", default=list, blank=True
    )

    class Meta:
        verbose_name = "línea de planilla"
        verbose_name_plural = "líneas de planilla"
        ordering = ["employee__last_name", "employee__first_name"]
        constraints = [
            models.UniqueConstraint(fields=["run", "employee"], name="unique_employee_per_run"),
        ]

    def __str__(self) -> str:
        return f"{self.run_id} · {self.employee_id}"


class PayrollLineItem(TenantAwareModel):
    line = models.ForeignKey(
        PayrollLine, verbose_name="línea", on_delete=models.CASCADE, related_name="items"
    )
    concept = models.ForeignKey(
        PayrollConcept,
        verbose_name="concepto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    code = models.CharField("código", max_length=30)
    name = models.CharField("nombre", max_length=120)
    kind = models.CharField("tipo", max_length=10, choices=PayrollConcept.Kind.choices)
    quantity = models.DecimalField(
        "cantidad", max_digits=10, decimal_places=2, null=True, blank=True
    )
    rate = models.DecimalField(
        "tarifa / tasa", max_digits=14, decimal_places=6, null=True, blank=True
    )
    amount = MoneyField("monto")
    cost_center = models.ForeignKey(
        "organization.CostCenter", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    detail = models.CharField("detalle", max_length=255, blank=True)
    deduction = models.ForeignKey(
        RecurringDeduction, on_delete=models.PROTECT, null=True, blank=True, related_name="items"
    )

    class Meta:
        verbose_name = "concepto de la línea"
        verbose_name_plural = "conceptos de la línea"
        ordering = ["line", "kind", "code"]

    def __str__(self) -> str:
        return f"{self.code} {self.amount}"


def payslip_upload_to(instance: "Payslip", filename: str) -> str:
    return f"tenants/{instance.tenant_id}/payslips/{instance.run_id}/{instance.number:07d}.pdf"


class Payslip(TenantAwareModel):
    """Comprobante de pago: numeración correlativa e inmutable. Una corrección emite un
    comprobante nuevo que referencia al anterior (`replaces`)."""

    number = models.PositiveIntegerField("número", editable=False)
    run = models.ForeignKey(
        PayrollRun, verbose_name="planilla", on_delete=models.PROTECT, related_name="payslips"
    )
    line = models.OneToOneField(
        PayrollLine, verbose_name="línea", on_delete=models.PROTECT, related_name="payslip"
    )
    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="payslips"
    )
    pdf = models.FileField("PDF", upload_to=payslip_upload_to, max_length=255)
    net = MoneyField("neto")
    replaces = models.ForeignKey(
        "self",
        verbose_name="reemplaza a",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    emailed_at = models.DateTimeField("enviado por correo", null=True, blank=True)
    emailed_to = models.EmailField("enviado a", blank=True)

    class Meta:
        verbose_name = "comprobante de pago"
        verbose_name_plural = "comprobantes de pago"
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "number"], name="unique_payslip_number"),
        ]

    def __str__(self) -> str:
        return f"Comprobante {self.number:07d}"
