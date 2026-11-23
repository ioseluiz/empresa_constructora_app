"""Expediente del empleado: datos personales, contratos, historial salarial, asignación a
proyectos y documentos.

Reglas que la base de datos garantiza (además de las validaciones de la API):
- Un empleado no puede tener dos contratos vigentes que se solapen en el tiempo.
- Un empleado no puede tener dos asignaciones solapadas al mismo proyecto.
- El salario se registra con vigencia (`valid_from`); la planilla toma el vigente en cada fecha.
"""

import uuid
from datetime import date
from decimal import Decimal
from pathlib import PurePath

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from apps.core.db import DateRange
from apps.core.models import TenantAwareModel
from apps.organization.panama import BANKS, CEDULA_REGEX, PROVINCES


class Employee(TenantAwareModel):
    class IdType(models.TextChoices):
        CEDULA = "cedula", "Cédula"
        PASSPORT = "passport", "Pasaporte"

    class Sex(models.TextChoices):
        MALE = "M", "Masculino"
        FEMALE = "F", "Femenino"

    class MaritalStatus(models.TextChoices):
        SINGLE = "single", "Soltero(a)"
        MARRIED = "married", "Casado(a)"
        UNION = "union", "Unido(a)"
        DIVORCED = "divorced", "Divorciado(a)"
        WIDOWED = "widowed", "Viudo(a)"

    class PaymentMethod(models.TextChoices):
        ACH = "ach", "Transferencia ACH"
        CHECK = "check", "Cheque"
        CASH = "cash", "Efectivo"

    class AccountType(models.TextChoices):
        SAVINGS = "savings", "Ahorros"
        CHECKING = "checking", "Corriente"

    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        TERMINATED = "terminated", "Retirado"

    code = models.CharField("número de empleado", max_length=20)
    first_name = models.CharField("primer nombre", max_length=60)
    middle_name = models.CharField("segundo nombre", max_length=60, blank=True)
    last_name = models.CharField("primer apellido", max_length=60)
    second_last_name = models.CharField("segundo apellido", max_length=60, blank=True)
    id_type = models.CharField(
        "tipo de identificación", max_length=10, choices=IdType.choices, default=IdType.CEDULA
    )
    id_number = models.CharField("número de identificación", max_length=30)
    css_number = models.CharField("número de seguro social", max_length=20, blank=True)
    birth_date = models.DateField("fecha de nacimiento", null=True, blank=True)
    sex = models.CharField("sexo", max_length=1, choices=Sex.choices, blank=True)
    marital_status = models.CharField(
        "estado civil", max_length=10, choices=MaritalStatus.choices, blank=True
    )
    nationality = models.CharField("nacionalidad", max_length=60, default="Panameña")
    email = models.EmailField("correo", blank=True)
    phone = models.CharField("teléfono", max_length=30, blank=True)
    address = models.CharField("dirección", max_length=255, blank=True)
    province = models.CharField("provincia", max_length=20, choices=PROVINCES, blank=True)
    emergency_contact_name = models.CharField("contacto de emergencia", max_length=120, blank=True)
    emergency_contact_phone = models.CharField("teléfono de emergencia", max_length=30, blank=True)
    payment_method = models.CharField(
        "forma de pago", max_length=10, choices=PaymentMethod.choices, default=PaymentMethod.ACH
    )
    bank = models.CharField("banco", max_length=20, choices=BANKS, blank=True)
    account_type = models.CharField(
        "tipo de cuenta", max_length=10, choices=AccountType.choices, blank=True
    )
    account_number = models.CharField(
        "número de cuenta",
        max_length=30,
        blank=True,
        validators=[RegexValidator(r"^\d{4,30}$", "Solo dígitos, sin guiones ni espacios.")],
    )
    hire_date = models.DateField("fecha de ingreso")
    termination_date = models.DateField("fecha de salida", null=True, blank=True)
    status = models.CharField(
        "estado", max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    is_union_member = models.BooleanField(
        "afiliado al sindicato",
        default=False,
        help_text="Se le descontará la cuota sindical en planilla.",
    )
    notes = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "empleado"
        verbose_name_plural = "empleados"
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_employee_code"),
            models.UniqueConstraint(
                fields=["tenant", "id_type", "id_number"], name="unique_employee_id_number"
            ),
            models.CheckConstraint(
                condition=Q(id_type="passport") | Q(id_number__regex=CEDULA_REGEX),
                name="employee_cedula_format",
            ),
            models.CheckConstraint(
                condition=~Q(payment_method="ach") | (~Q(bank="") & ~Q(account_number="")),
                name="employee_ach_requires_account",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.full_name}"

    @property
    def full_name(self) -> str:
        parts = [self.first_name, self.middle_name, self.last_name, self.second_last_name]
        return " ".join(p for p in parts if p)

    def contract_on(self, on: date) -> "EmploymentContract | None":
        return (
            self.contracts.exclude(status=EmploymentContract.Status.CANCELLED)
            .filter(start_date__lte=on)
            .filter(Q(end_date__isnull=True) | Q(end_date__gte=on))
            .first()
        )


class EmploymentContract(TenantAwareModel):
    """Contrato de trabajo (Código de Trabajo de Panamá, arts. 73-77)."""

    class Type(models.TextChoices):
        INDEFINITE = "indefinite", "Tiempo indefinido"
        FIXED_TERM = "fixed_term", "Tiempo definido"
        PROJECT = "project", "Obra determinada"

    class PayFrequency(models.TextChoices):
        WEEKLY = "weekly", "Semanal"
        BIWEEKLY = "biweekly", "Quincenal"
        MONTHLY = "monthly", "Mensual"

    class PayBasis(models.TextChoices):
        MONTHLY = "monthly", "Salario mensual"
        HOURLY = "hourly", "Por hora"

    class Shift(models.TextChoices):
        DAY = "day", "Diurna"
        NIGHT = "night", "Nocturna"
        MIXED = "mixed", "Mixta"

    class Status(models.TextChoices):
        ACTIVE = "active", "Vigente"
        ENDED = "ended", "Terminado"
        CANCELLED = "cancelled", "Anulado"

    employee = models.ForeignKey(
        Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="contracts"
    )
    contract_type = models.CharField("tipo de contrato", max_length=12, choices=Type.choices)
    start_date = models.DateField("inicio")
    end_date = models.DateField("fin", null=True, blank=True)
    position = models.ForeignKey(
        "organization.Position", verbose_name="puesto", on_delete=models.PROTECT, related_name="+"
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="obra",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Obligatorio en contratos por obra determinada.",
    )
    cost_center = models.ForeignKey(
        "organization.CostCenter",
        verbose_name="centro de costo",
        on_delete=models.PROTECT,
        related_name="+",
        help_text="Centro de costo al que se carga la planilla por defecto.",
    )
    pay_frequency = models.CharField(
        "frecuencia de pago", max_length=10, choices=PayFrequency.choices
    )
    pay_basis = models.CharField("base de pago", max_length=10, choices=PayBasis.choices)
    shift = models.CharField("jornada", max_length=10, choices=Shift.choices, default=Shift.DAY)
    weekly_hours = models.DecimalField(
        "horas semanales", max_digits=4, decimal_places=1, default=Decimal("48")
    )
    applies_cba = models.BooleanField("aplica convención SUNTRACS–CAPAC", default=False)
    cba_category = models.ForeignKey(
        "organization.CBACategory",
        verbose_name="categoría de convención",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    end_reason = models.CharField("motivo de terminación", max_length=255, blank=True)
    notes = models.TextField("observaciones", blank=True)

    class Meta:
        verbose_name = "contrato"
        verbose_name_plural = "contratos"
        ordering = ["employee", "-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="contract_dates_consistent",
            ),
            models.CheckConstraint(
                condition=~Q(contract_type="fixed_term") | Q(end_date__isnull=False),
                name="fixed_term_contract_has_end",
            ),
            models.CheckConstraint(
                condition=~Q(contract_type="project") | Q(project__isnull=False),
                name="project_contract_has_project",
            ),
            models.CheckConstraint(
                condition=Q(applies_cba=False) | Q(cba_category__isnull=False),
                name="cba_contract_has_category",
            ),
            ExclusionConstraint(
                name="exclude_overlapping_contracts",
                expressions=[
                    (DateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                    ("employee", RangeOperators.EQUAL),
                ],
                condition=~Q(status="cancelled"),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_contract_type_display()} desde {self.start_date:%d/%m/%Y}"

    def salary_on(self, on: date) -> "SalaryRecord | None":
        return self.salary_history.filter(valid_from__lte=on).order_by("-valid_from").first()


class SalaryRecord(TenantAwareModel):
    """Salario o tarifa vigente desde una fecha. Un aumento es un registro nuevo; nunca se
    sobreescribe el anterior (la planilla de períodos pasados debe poder recalcularse)."""

    contract = models.ForeignKey(
        EmploymentContract,
        verbose_name="contrato",
        on_delete=models.PROTECT,
        related_name="salary_history",
    )
    valid_from = models.DateField("vigente desde")
    amount = models.DecimalField(
        "monto",
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Salario mensual o tarifa por hora, según la base de pago del contrato.",
    )
    uses_cba_rate = models.BooleanField(
        "usa la tarifa de la convención",
        default=False,
        help_text="La tarifa por hora sigue la tabla de la convención vigente en cada fecha.",
    )
    reason = models.CharField("motivo", max_length=255, blank=True)

    class Meta:
        verbose_name = "registro salarial"
        verbose_name_plural = "historial salarial"
        ordering = ["contract", "-valid_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["contract", "valid_from"], name="unique_salary_per_date"
            ),
            models.CheckConstraint(
                condition=(Q(uses_cba_rate=True) & Q(amount__isnull=True))
                | (Q(uses_cba_rate=False) & Q(amount__gt=Decimal("0"))),
                name="salary_amount_or_cba",
            ),
        ]

    def __str__(self) -> str:
        value = "tarifa de convención" if self.uses_cba_rate else f"B/.{self.amount}"
        return f"{value} desde {self.valid_from:%d/%m/%Y}"


class ProjectAssignment(TenantAwareModel):
    """Asignación del empleado a una obra. Define en qué proyectos aparece (y quién lo ve con
    roles limitados por proyecto). Las horas por proyecto vendrán de las marcaciones."""

    employee = models.ForeignKey(
        Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="assignments"
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    position = models.ForeignKey(
        "organization.Position",
        verbose_name="puesto en la obra",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta", null=True, blank=True)
    notes = models.CharField("observaciones", max_length=255, blank=True)

    class Meta:
        verbose_name = "asignación a proyecto"
        verbose_name_plural = "asignaciones a proyectos"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="assignment_dates_consistent",
            ),
            ExclusionConstraint(
                name="exclude_overlapping_assignments",
                expressions=[
                    (DateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                    ("employee", RangeOperators.EQUAL),
                    ("project", RangeOperators.EQUAL),
                ],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee.code} en {self.project.code}"


def document_upload_to(instance: "EmployeeDocument", filename: str) -> str:
    # Nombre aleatorio: el nombre original (que puede contener datos personales) se guarda
    # aparte y no forma parte de la ruta.
    ext = PurePath(filename).suffix.lower()
    return f"tenants/{instance.tenant_id}/employees/{instance.employee_id}/{uuid.uuid4().hex}{ext}"


class EmployeeDocument(TenantAwareModel):
    class Kind(models.TextChoices):
        ID_COPY = "id_copy", "Copia de cédula o pasaporte"
        CSS_CARD = "css_card", "Carné del seguro social"
        CONTRACT = "contract", "Contrato firmado"
        WORK_PERMIT = "work_permit", "Permiso de trabajo"
        CERTIFICATE = "certificate", "Certificado o diploma"
        MEDICAL = "medical", "Certificado médico"
        OTHER = "other", "Otro"

    employee = models.ForeignKey(
        Employee, verbose_name="empleado", on_delete=models.PROTECT, related_name="documents"
    )
    kind = models.CharField("tipo", max_length=12, choices=Kind.choices)
    title = models.CharField("descripción", max_length=150, blank=True)
    file = models.FileField("archivo", upload_to=document_upload_to, max_length=255)
    original_name = models.CharField("nombre original", max_length=255)
    content_type = models.CharField("tipo de archivo", max_length=100)
    size = models.PositiveIntegerField("tamaño (bytes)")
    expires_on = models.DateField("vence", null=True, blank=True)

    class Meta:
        verbose_name = "documento del empleado"
        verbose_name_plural = "documentos del empleado"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title or self.get_kind_display()
