"""Usuario de la plataforma. Se identifica por correo electrónico.

Un usuario es global (no pertenece a un tenant): su acceso a cada empresa se
define con `tenants.Membership`, lo que permite que un contador externo
atienda varias empresas con una sola cuenta.
"""

import uuid
from typing import Any, ClassVar

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def _create_user(self, email: str, password: str | None, **extra: Any) -> "User":
        if not email:
            raise ValueError("El correo es obligatorio.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> "User":
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create_user(email, password, **extra)

    def get_by_natural_key(self, username: str | None) -> "User":
        return self.get(email__iexact=username)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField("correo electrónico", unique=True)
    first_name = models.CharField("nombre", max_length=150, blank=True)
    last_name = models.CharField("apellido", max_length=150, blank=True)
    is_active = models.BooleanField("activo", default=True)
    is_staff = models.BooleanField(
        "acceso al admin",
        default=False,
        help_text="Solo personal de la plataforma (soporte SaaS).",
    )
    date_joined = models.DateTimeField("fecha de registro", default=timezone.now)

    # Autenticación de dos factores (TOTP). El secreto se guarda cifrado (ver mfa.py).
    mfa_enabled = models.BooleanField("MFA activo", default=False)
    mfa_secret = models.TextField(blank=True, editable=False)
    mfa_last_used_step = models.BigIntegerField(default=0, editable=False)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"
        ordering = ["email"]

    def __str__(self) -> str:
        return self.email

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = self.email.lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email


class MFARecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_recovery_codes")
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "código de recuperación MFA"
        verbose_name_plural = "códigos de recuperación MFA"

    def __str__(self) -> str:
        return f"Código de {self.user}"


class SecurityEvent(models.Model):
    """Eventos de seguridad de la cuenta (no pertenecen a una empresa)."""

    class Type(models.TextChoices):
        LOGIN_SUCCESS = "login_success", "Inicio de sesión"
        LOGIN_FAILED = "login_failed", "Inicio de sesión fallido"
        LOGOUT = "logout", "Cierre de sesión"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "Solicitud de recuperación"
        PASSWORD_RESET_DONE = "password_reset_done", "Contraseña restablecida"
        PASSWORD_CHANGED = "password_changed", "Contraseña cambiada"
        MFA_ENABLED = "mfa_enabled", "MFA activado"
        MFA_DISABLED = "mfa_disabled", "MFA desactivado"
        MFA_FAILED = "mfa_failed", "Código MFA incorrecto"
        MFA_RECOVERY_USED = "mfa_recovery_used", "Código de recuperación usado"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="security_events"
    )
    email = models.EmailField(blank=True)
    type = models.CharField(max_length=32, choices=Type.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "evento de seguridad"
        verbose_name_plural = "eventos de seguridad"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_type_display()} {self.email}"
