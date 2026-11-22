from django.db import models

from apps.core.models import MoneyField, TenantAwareModel
from apps.organization.panama import PROVINCES


class Project(TenantAwareModel):
    """Obra de construcción. Tiene su propio centro de costo (1:1) al que se imputan la planilla
    y, en fases futuras, compras, inventario y contabilidad."""

    class Status(models.TextChoices):
        PLANNING = "planning", "En planificación"
        ACTIVE = "active", "En ejecución"
        SUSPENDED = "suspended", "Suspendido"
        FINISHED = "finished", "Terminado"

    code = models.CharField("código", max_length=30)
    name = models.CharField("nombre", max_length=200)
    client = models.CharField("cliente", max_length=200, blank=True)
    province = models.CharField("provincia", max_length=20, choices=PROVINCES, blank=True)
    address = models.CharField("dirección / ubicación", max_length=255, blank=True)
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.PLANNING
    )
    start_date = models.DateField("fecha de inicio", null=True, blank=True)
    estimated_end_date = models.DateField("fin estimado", null=True, blank=True)
    actual_end_date = models.DateField("fin real", null=True, blank=True)
    contract_amount = MoneyField("monto del contrato", null=True, blank=True, default=None)
    description = models.TextField("descripción", blank=True)
    cost_center = models.OneToOneField(
        "organization.CostCenter",
        verbose_name="centro de costo",
        on_delete=models.PROTECT,
        related_name="project",
        editable=False,
    )

    class Meta:
        verbose_name = "proyecto"
        verbose_name_plural = "proyectos"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="unique_project_code"),
            models.CheckConstraint(
                condition=models.Q(estimated_end_date__isnull=True)
                | models.Q(start_date__isnull=True)
                | models.Q(estimated_end_date__gte=models.F("start_date")),
                name="project_dates_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"
