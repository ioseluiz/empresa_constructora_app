"""Bitácora de auditoría por empresa. Es de solo inserción: un trigger de PostgreSQL
rechaza UPDATE y DELETE (ver migración 0001)."""

import uuid

from django.conf import settings
from django.db import models

from apps.core.models import TenantManager


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "Creación"
        UPDATE = "update", "Modificación"
        DELETE = "delete", "Eliminación"
        INVITE = "invite", "Invitación"
        ACCEPT = "accept", "Aceptación"
        REVOKE = "revoke", "Revocación"
        APPROVE = "approve", "Aprobación"
        EXPORT = "export", "Exportación"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant", verbose_name="empresa", on_delete=models.PROTECT, related_name="+"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    actor_email = models.EmailField("correo del usuario", blank=True)
    action = models.CharField("acción", max_length=20, choices=Action.choices)
    object_type = models.CharField("tipo de objeto", max_length=100)
    object_id = models.CharField("id del objeto", max_length=64, blank=True)
    object_repr = models.CharField("descripción", max_length=255, blank=True)
    changes = models.JSONField("cambios", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("IP", null=True, blank=True)
    user_agent = models.CharField("navegador", max_length=255, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    objects = TenantManager()
    all_tenants = models.Manager()  # noqa: DJ012

    class Meta:
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"
        ordering = ["-created_at"]
        base_manager_name = "all_tenants"
        indexes = [
            models.Index(fields=["tenant", "object_type", "object_id"]),
            models.Index(fields=["tenant", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.get_action_display()} {self.object_type} {self.object_repr}"
