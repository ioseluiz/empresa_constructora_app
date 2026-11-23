"""Marcaciones de entrada y salida (docs/PLAN.md §4.3).

Principios:
- Una marcación (`Punch`) nunca se edita ni se borra. Una corrección crea una marcación nueva
  (`corrects` → la original) y anula la original con motivo; la base de datos impide cambiar
  empleado, fecha/hora, tipo u origen de una marcación existente (trigger).
- No puede haber dos marcaciones vigentes del mismo empleado en el mismo segundo: así se
  detectan los duplicados al reimportar un archivo.
- Las horas se guardan con zona horaria; los archivos del reloj traen hora local de la empresa.
"""

from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import ArrayField, RangeOperators
from django.db import models
from django.db.models import Q

from apps.core.db import DateRange
from apps.core.models import TenantAwareModel


class Device(TenantAwareModel):
    """Reloj biométrico u otro equipo de marcación."""

    class Brand(models.TextChoices):
        ZKTECO = "zkteco", "ZKTeco"
        OTHER = "other", "Otro"

    name = models.CharField("nombre", max_length=120)
    brand = models.CharField("marca", max_length=10, choices=Brand.choices, default=Brand.ZKTECO)
    model = models.CharField("modelo", max_length=60, blank=True)
    serial_number = models.CharField("número de serie", max_length=60, blank=True)
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="devices",
        help_text="Vacío = oficina central.",
    )
    location = models.CharField("ubicación", max_length=150, blank=True)
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "reloj de marcación"
        verbose_name_plural = "relojes de marcación"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "serial_number"],
                condition=~Q(serial_number=""),
                name="unique_device_serial",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ClockCode(TenantAwareModel):
    """Código con el que el empleado está registrado en el reloj (PIN / ID de usuario).
    Sin reloj = vale para todos los relojes de la empresa."""

    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="clock_codes"
    )
    device = models.ForeignKey(
        Device,
        verbose_name="reloj",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="codes",
    )
    code = models.CharField("código en el reloj", max_length=30)

    class Meta:
        verbose_name = "código de reloj"
        verbose_name_plural = "códigos de reloj"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "device", "code"],
                condition=Q(device__isnull=False),
                name="unique_clock_code_per_device",
            ),
            models.UniqueConstraint(
                fields=["tenant", "code"],
                condition=Q(device__isnull=True),
                name="unique_global_clock_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} → {self.employee_id}"


class ImportTemplate(TenantAwareModel):
    """Plantilla de mapeo de columnas para Excel/CSV de otros sistemas. Las columnas se indican
    por nombre de encabezado o por número (1 = primera columna)."""

    class EmployeeKey(models.TextChoices):
        CLOCK_CODE = "clock_code", "Código de reloj"
        EMPLOYEE_CODE = "employee_code", "Número de empleado"
        ID_NUMBER = "id_number", "Cédula / pasaporte"

    name = models.CharField("nombre", max_length=120)
    has_header = models.BooleanField("primera fila es encabezado", default=True)
    delimiter = models.CharField(
        "separador (CSV)", max_length=1, blank=True, help_text="Vacío = detectar automáticamente."
    )
    employee_key = models.CharField(
        "identifica al empleado por",
        max_length=15,
        choices=EmployeeKey.choices,
        default=EmployeeKey.CLOCK_CODE,
    )
    employee_column = models.CharField("columna de empleado", max_length=60)
    datetime_column = models.CharField(
        "columna de fecha y hora",
        max_length=60,
        blank=True,
        help_text="Si fecha y hora vienen juntas. Si no, usa las columnas de fecha y de hora.",
    )
    date_column = models.CharField("columna de fecha", max_length=60, blank=True)
    time_column = models.CharField("columna de hora", max_length=60, blank=True)
    date_format = models.CharField(
        "formato de fecha",
        max_length=30,
        default="%d/%m/%Y",
        help_text="Formato strftime, p. ej. %d/%m/%Y o %Y-%m-%d.",
    )
    time_format = models.CharField("formato de hora", max_length=30, default="%H:%M")
    direction_column = models.CharField(
        "columna de tipo (entrada/salida)", max_length=60, blank=True
    )
    in_values = models.CharField(
        "valores de entrada", max_length=120, default="E,ENTRADA,IN,I,0", blank=True
    )
    out_values = models.CharField(
        "valores de salida", max_length=120, default="S,SALIDA,OUT,O,1", blank=True
    )
    device_column = models.CharField(
        "columna de reloj (nº de serie o nombre)", max_length=60, blank=True
    )

    class Meta:
        verbose_name = "plantilla de importación"
        verbose_name_plural = "plantillas de importación"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_import_template_name"),
        ]

    def __str__(self) -> str:
        return self.name


def batch_upload_to(instance: "ImportBatch", filename: str) -> str:
    from pathlib import PurePath
    from uuid import uuid4

    return (
        f"tenants/{instance.tenant_id}/timeclock/{uuid4().hex}{PurePath(filename).suffix.lower()}"
    )


class ImportBatch(TenantAwareModel):
    """Lote de importación: archivo → vista previa → confirmación (o reversión)."""

    class Source(models.TextChoices):
        ZKTECO = "zkteco", "Reloj ZKTeco (attlog)"
        TEMPLATE = "template", "Excel / CSV con plantilla"

    class Status(models.TextChoices):
        PENDING = "pending", "En cola"
        PROCESSING = "processing", "Procesando"
        PREVIEW = "preview", "Lista para confirmar"
        CONFIRMED = "confirmed", "Confirmada"
        REVERTED = "reverted", "Revertida"
        DISCARDED = "discarded", "Descartada"
        FAILED = "failed", "Error"

    source = models.CharField("origen", max_length=10, choices=Source.choices)
    template = models.ForeignKey(
        ImportTemplate,
        verbose_name="plantilla",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    device = models.ForeignKey(
        Device,
        verbose_name="reloj",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Reloj de origen (obligatorio en archivos ZKTeco).",
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        help_text="Proyecto de las marcaciones cuando el reloj no lo indica.",
    )
    file = models.FileField("archivo", upload_to=batch_upload_to, max_length=255)
    original_name = models.CharField("nombre original", max_length=255)
    status = models.CharField(
        "estado", max_length=12, choices=Status.choices, default=Status.PENDING
    )
    error = models.TextField("error", blank=True)
    total_rows = models.PositiveIntegerField("filas", default=0)
    valid_rows = models.PositiveIntegerField("válidas", default=0)
    error_rows = models.PositiveIntegerField("con error", default=0)
    duplicate_rows = models.PositiveIntegerField("duplicadas", default=0)
    first_punch = models.DateTimeField("primera marcación", null=True, blank=True)
    last_punch = models.DateTimeField("última marcación", null=True, blank=True)
    confirmed_at = models.DateTimeField("confirmado", null=True, blank=True)
    confirmed_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    reverted_at = models.DateTimeField("revertido", null=True, blank=True)
    reverted_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    revert_reason = models.CharField("motivo de reversión", max_length=255, blank=True)

    class Meta:
        verbose_name = "lote de importación"
        verbose_name_plural = "lotes de importación"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_source_display()} · {self.original_name}"


class ImportRow(TenantAwareModel):
    """Fila interpretada del archivo (vista previa). Al confirmar, las válidas se vuelven Punch."""

    class Status(models.TextChoices):
        VALID = "valid", "Válida"
        ERROR = "error", "Con error"
        DUPLICATE = "duplicate", "Duplicada"

    batch = models.ForeignKey(
        ImportBatch, verbose_name="lote", on_delete=models.CASCADE, related_name="rows"
    )
    row_number = models.PositiveIntegerField("fila")
    raw = models.CharField("contenido", max_length=500, blank=True)
    raw_code = models.CharField("código", max_length=60, blank=True)
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    timestamp = models.DateTimeField("fecha y hora", null=True, blank=True)
    direction = models.CharField("tipo", max_length=7, blank=True)
    device = models.ForeignKey(
        Device, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    status = models.CharField("estado", max_length=10, choices=Status.choices)
    message = models.CharField("mensaje", max_length=255, blank=True)

    class Meta:
        verbose_name = "fila importada"
        verbose_name_plural = "filas importadas"
        ordering = ["batch", "row_number"]
        indexes = [models.Index(fields=["batch", "status"])]


class Punch(TenantAwareModel):
    class Direction(models.TextChoices):
        IN = "in", "Entrada"
        OUT = "out", "Salida"
        UNKNOWN = "unknown", "Sin tipo"

    class Source(models.TextChoices):
        DEVICE = "device", "Reloj"
        FILE = "file", "Archivo"
        MANUAL = "manual", "Manual"
        APP = "app", "App móvil"

    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="punches"
    )
    timestamp = models.DateTimeField("fecha y hora")
    direction = models.CharField(
        "tipo", max_length=7, choices=Direction.choices, default=Direction.UNKNOWN
    )
    source = models.CharField("origen", max_length=7, choices=Source.choices)
    device = models.ForeignKey(
        Device,
        verbose_name="reloj",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="punches",
    )
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="punches",
    )
    batch = models.ForeignKey(
        ImportBatch,
        verbose_name="lote",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="punches",
    )
    corrects = models.ForeignKey(
        "self",
        verbose_name="corrige a",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
    )
    reason = models.CharField("motivo", max_length=255, blank=True)
    is_void = models.BooleanField("anulada", default=False)
    voided_at = models.DateTimeField("anulada el", null=True, blank=True)
    voided_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    void_reason = models.CharField("motivo de anulación", max_length=255, blank=True)

    class Meta:
        verbose_name = "marcación"
        verbose_name_plural = "marcaciones"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["tenant", "employee", "timestamp"]),
            models.Index(fields=["tenant", "project", "timestamp"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "timestamp"],
                condition=Q(is_void=False),
                name="unique_active_punch_per_second",
            ),
            models.CheckConstraint(
                condition=~Q(source="manual") | ~Q(reason=""),
                name="manual_punch_requires_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.timestamp:%Y-%m-%d %H:%M} {self.direction}"


def default_workdays() -> list[int]:
    return [0, 1, 2, 3, 4]  # lunes a viernes (0 = lunes … 6 = domingo)


class Shift(TenantAwareModel):
    """Horario de trabajo. Si la salida es menor o igual que la entrada, cruza la medianoche."""

    code = models.CharField("código", max_length=20)
    name = models.CharField("nombre", max_length=120)
    start_time = models.TimeField("entrada")
    end_time = models.TimeField("salida")
    break_minutes = models.PositiveSmallIntegerField(
        "almuerzo / descanso (min)",
        default=60,
        help_text="Se descuenta cuando no hay marcaciones de salida y regreso del almuerzo.",
    )
    break_after_minutes = models.PositiveSmallIntegerField(
        "descontar descanso si la jornada supera (min)", default=360
    )
    workdays = ArrayField(
        models.PositiveSmallIntegerField(),
        verbose_name="días laborables",
        default=default_workdays,
        help_text="0 = lunes … 6 = domingo. Los demás días son de descanso.",
    )
    late_tolerance_minutes = models.PositiveSmallIntegerField(
        "tolerancia de llegada (min)", default=5
    )
    overtime_rounding_minutes = models.PositiveSmallIntegerField(
        "redondeo de horas extra (min)",
        default=15,
        help_text="Las extras se cuentan en bloques completos de estos minutos (0 = sin redondeo).",
    )
    count_early_arrival = models.BooleanField(
        "contar llegada anticipada",
        default=False,
        help_text="Si no se marca, el tiempo antes de la hora de entrada no se paga.",
    )
    is_default = models.BooleanField(
        "horario por defecto", default=False, help_text="Para empleados sin horario asignado."
    )
    is_active = models.BooleanField("activo", default=True)

    class Meta:
        verbose_name = "horario"
        verbose_name_plural = "horarios"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_shift_code"),
            models.UniqueConstraint(
                fields=["tenant"], condition=Q(is_default=True), name="single_default_shift"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.start_time:%H:%M}–{self.end_time:%H:%M})"

    @property
    def crosses_midnight(self) -> bool:
        return self.end_time <= self.start_time

    @property
    def span_minutes(self) -> int:
        start = self.start_time.hour * 60 + self.start_time.minute
        end = self.end_time.hour * 60 + self.end_time.minute
        return (end - start) % (24 * 60) or 24 * 60

    @property
    def paid_minutes(self) -> int:
        deduct = self.break_minutes if self.span_minutes > self.break_after_minutes else 0
        return self.span_minutes - deduct


class ShiftAssignment(TenantAwareModel):
    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="shifts"
    )
    shift = models.ForeignKey(
        Shift, verbose_name="horario", on_delete=models.PROTECT, related_name="assignments"
    )
    start_date = models.DateField("desde")
    end_date = models.DateField("hasta", null=True, blank=True)

    class Meta:
        verbose_name = "asignación de horario"
        verbose_name_plural = "asignaciones de horario"
        ordering = ["-start_date"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=models.F("start_date")),
                name="shift_assignment_dates_consistent",
            ),
            ExclusionConstraint(
                name="exclude_overlapping_shift_assignments",
                expressions=[
                    (DateRange("start_date", "end_date"), RangeOperators.OVERLAPS),
                    ("employee", RangeOperators.EQUAL),
                ],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} → {self.shift_id} desde {self.start_date}"


class WorkDay(TenantAwareModel):
    """Jornada calculada por el motor a partir de las marcaciones. Al aprobarla se generan las
    horas (`attendance.TimeEntry`) que usa la planilla."""

    class DayKind(models.TextChoices):
        REGULAR = "regular", "Laborable"
        REST = "rest", "Descanso"
        HOLIDAY = "holiday", "Feriado"

    class Jornada(models.TextChoices):
        DAY = "day", "Diurna"
        NIGHT = "night", "Nocturna"
        MIXED = "mixed", "Mixta"

    class Status(models.TextChoices):
        PENDING = "pending", "Por aprobar"
        REVIEW = "review", "Con inconsistencias"
        APPROVED = "approved", "Aprobada"

    employee = models.ForeignKey(
        "hr.Employee", verbose_name="empleado", on_delete=models.PROTECT, related_name="workdays"
    )
    date = models.DateField("fecha")
    project = models.ForeignKey(
        "projects.Project",
        verbose_name="proyecto",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="workdays",
    )
    shift = models.ForeignKey(
        Shift,
        verbose_name="horario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    day_kind = models.CharField("tipo de día", max_length=8, choices=DayKind.choices)
    jornada = models.CharField("jornada", max_length=5, choices=Jornada.choices, blank=True)
    first_in = models.DateTimeField("entrada", null=True, blank=True)
    last_out = models.DateTimeField("salida", null=True, blank=True)
    segments = models.JSONField("tramos trabajados", default=list, blank=True)
    worked_minutes = models.PositiveIntegerField("minutos trabajados", default=0)
    break_minutes = models.PositiveIntegerField("descanso descontado", default=0)
    ordinary_minutes = models.PositiveIntegerField("ordinarios", default=0)
    overtime_day_minutes = models.PositiveIntegerField("extra diurna", default=0)
    overtime_night_minutes = models.PositiveIntegerField("extra nocturna", default=0)
    overtime_mixed_minutes = models.PositiveIntegerField(
        "extra mixta (prolongación nocturna)", default=0
    )
    late_minutes = models.PositiveIntegerField("tardanza", default=0)
    missing_minutes = models.PositiveIntegerField("faltante", default=0)
    issues = ArrayField(
        models.CharField(max_length=30), verbose_name="inconsistencias", default=list, blank=True
    )
    status = models.CharField(
        "estado", max_length=8, choices=Status.choices, default=Status.PENDING
    )
    approved_at = models.DateTimeField("aprobada el", null=True, blank=True)
    approved_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    notes = models.CharField("observaciones", max_length=255, blank=True)

    class Meta:
        verbose_name = "jornada"
        verbose_name_plural = "jornadas"
        ordering = ["-date", "employee"]
        indexes = [models.Index(fields=["tenant", "date", "status"])]
        constraints = [
            models.UniqueConstraint(fields=["employee", "date"], name="unique_workday_per_date"),
        ]

    def __str__(self) -> str:
        return f"{self.employee_id} {self.date}"

    @property
    def overtime_minutes(self) -> int:
        return self.overtime_day_minutes + self.overtime_night_minutes + self.overtime_mixed_minutes
