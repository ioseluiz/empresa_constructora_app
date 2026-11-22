"""Empresa cliente del SaaS (tenant) y la membresía de usuarios a cada empresa.

Estas dos tablas NO tienen Row-Level Security: se consultan antes de saber qué empresa
está activa (login, selector de empresa).
"""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Tenant(BaseModel):
    name = models.CharField("nombre comercial", max_length=200)
    legal_name = models.CharField("razón social", max_length=250, blank=True)
    slug = models.SlugField("identificador", max_length=63, unique=True)
    ruc = models.CharField("RUC", max_length=30, blank=True)
    dv = models.CharField("DV", max_length=2, blank=True, help_text="Dígito verificador del RUC")
    country = models.CharField("país", max_length=2, default="PA")
    currency = models.CharField("moneda funcional", max_length=3, default="USD")
    timezone = models.CharField("zona horaria", max_length=64, default="America/Panama")
    is_active = models.BooleanField("activa", default=True)
    require_mfa = models.BooleanField(
        "exigir verificación en dos pasos",
        default=False,
        help_text="Los usuarios sin MFA no podrán acceder a los datos de la empresa.",
    )

    class Meta:
        verbose_name = "empresa"
        verbose_name_plural = "empresas"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Membership(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    tenant = models.ForeignKey(
        Tenant, verbose_name="empresa", on_delete=models.CASCADE, related_name="memberships"
    )
    is_owner = models.BooleanField(
        "propietario",
        default=False,
        help_text="Administrador principal de la empresa: tiene todos los permisos.",
    )
    is_active = models.BooleanField("activa", default=True)

    class Meta:
        verbose_name = "membresía"
        verbose_name_plural = "membresías"
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="unique_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.user} @ {self.tenant}"
