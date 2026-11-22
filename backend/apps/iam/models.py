import hashlib
import secrets
from datetime import timedelta
from typing import Any

from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TenantAwareModel

from .catalog import PERMISSION_CODES


def validate_permission_codes(codes: list[str]) -> None:
    unknown = set(codes) - PERMISSION_CODES
    if unknown:
        raise ValidationError(f"Permisos desconocidos: {', '.join(sorted(unknown))}")


class Role(TenantAwareModel):
    name = models.CharField("nombre", max_length=100)
    description = models.CharField("descripción", max_length=255, blank=True)
    permissions = ArrayField(
        models.CharField(max_length=64),
        verbose_name="permisos",
        default=list,
        blank=True,
        validators=[validate_permission_codes],
    )
    is_system = models.BooleanField(
        "plantilla del sistema", default=False, help_text="Creado automáticamente con la empresa."
    )

    class Meta:
        verbose_name = "rol"
        verbose_name_plural = "roles"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="unique_role_name_per_tenant"),
        ]

    def __str__(self) -> str:
        return self.name


class RoleAssignment(TenantAwareModel):
    """Rol asignado a un miembro. Alcance actual: toda la empresa.
    En el Sprint 4 se agrega `projects` (M2M) para limitar el rol a obras específicas."""

    membership = models.ForeignKey(
        "tenants.Membership",
        verbose_name="miembro",
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )
    role = models.ForeignKey(
        Role, verbose_name="rol", on_delete=models.PROTECT, related_name="assignments"
    )

    class Meta:
        verbose_name = "asignación de rol"
        verbose_name_plural = "asignaciones de rol"
        constraints = [
            models.UniqueConstraint(fields=["membership", "role"], name="unique_role_assignment"),
        ]

    def __str__(self) -> str:
        return f"{self.membership} → {self.role}"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Invitation(TenantAwareModel):
    INVITATION_TTL = timedelta(days=7)

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        ACCEPTED = "accepted", "Aceptada"
        REVOKED = "revoked", "Revocada"

    email = models.EmailField("correo")
    roles = models.ManyToManyField(Role, verbose_name="roles", related_name="+", blank=True)
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    status = models.CharField(
        "estado", max_length=10, choices=Status.choices, default=Status.PENDING
    )
    expires_at = models.DateTimeField("vence")
    accepted_at = models.DateTimeField("aceptada", null=True, blank=True)

    class Meta:
        verbose_name = "invitación"
        verbose_name_plural = "invitaciones"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "email"],
                condition=models.Q(status="pending"),
                name="unique_pending_invitation",
            ),
        ]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    def issue_token(self) -> str:
        """Genera un token nuevo; solo se guarda su hash. Devuelve el token en claro
        para enviarlo por correo (nunca se vuelve a poder leer)."""
        token = secrets.token_urlsafe(32)
        self.token_hash = hash_token(token)
        self.expires_at = timezone.now() + self.INVITATION_TTL
        return token

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_usable(self) -> bool:
        return self.status == self.Status.PENDING and not self.is_expired
