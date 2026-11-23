"""Marcaciones de entrada y salida (docs/PLAN.md §4.3).

Principios:
- Una marcación (`Punch`) nunca se edita ni se borra. Una corrección crea una marcación nueva
  (`corrects` → la original) y anula la original con motivo; la base de datos impide cambiar
  empleado, fecha/hora, tipo u origen de una marcación existente (trigger).
- No puede haber dos marcaciones vigentes del mismo empleado en el mismo segundo: así se
  detectan los duplicados al reimportar un archivo.
- Las horas se guardan con zona horaria; los archivos del reloj traen hora local de la empresa.
"""

from django.db import models
from django.db.models import Q

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
