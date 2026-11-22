"""MFA con TOTP (RFC 6238): compatible con Google Authenticator, Microsoft Authenticator,
Authy, 1Password, etc.

- El secreto se cifra en reposo con Fernet (clave MFA_ENCRYPTION_KEY o derivada de SECRET_KEY).
- Un código ya usado no se acepta de nuevo (protección contra repetición).
- Códigos de recuperación de un solo uso, guardados como hash SHA-256.
"""

import base64
import hashlib
import secrets
import time

import pyotp
import segno
from cryptography.fernet import Fernet
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from .models import MFARecoveryCode, User

ISSUER = "Constructora"
STEP_SECONDS = 30
RECOVERY_CODE_COUNT = 10
LOGIN_TOKEN_SALT = "accounts.mfa.login"  # noqa: S105 — sal de firma, no contraseña
LOGIN_TOKEN_MAX_AGE = 300  # 5 minutos para escribir el código


def _fernet() -> Fernet:
    key = (
        settings.MFA_ENCRYPTION_KEY
        or base64.urlsafe_b64encode(
            hashlib.sha256(f"mfa:{settings.SECRET_KEY}".encode()).digest()
        ).decode()
    )
    return Fernet(key.encode())


def _decrypt(user: User) -> str:
    return _fernet().decrypt(user.mfa_secret.encode()).decode()


def start_setup(user: User) -> dict[str, str]:
    """Genera un secreto nuevo (pendiente hasta confirmar con un código)."""
    secret = pyotp.random_base32()
    user.mfa_secret = _fernet().encrypt(secret.encode()).decode()
    user.save(update_fields=["mfa_secret"])
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)
    qr_svg = segno.make(uri, error="m").svg_inline(scale=5, border=2, dark="#0f172a")
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": qr_svg}


def verify_totp(user: User, code: str) -> bool:
    if not user.mfa_secret or not code.isdigit() or len(code) != 6:
        return False
    totp = pyotp.TOTP(_decrypt(user))
    now_step = int(time.time()) // STEP_SECONDS
    for step in (now_step - 1, now_step, now_step + 1):  # tolera ±30 s de desfase de reloj
        if step > user.mfa_last_used_step and secrets.compare_digest(
            totp.at(step * STEP_SECONDS), code
        ):
            user.mfa_last_used_step = step
            user.save(update_fields=["mfa_last_used_step"])
            return True
    return False


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").upper().encode()).hexdigest()


@transaction.atomic
def generate_recovery_codes(user: User) -> list[str]:
    user.mfa_recovery_codes.all().delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = base64.b32encode(secrets.token_bytes(5)).decode()  # 8 caracteres
        codes.append(f"{raw[:4]}-{raw[4:]}")
    MFARecoveryCode.objects.bulk_create(
        MFARecoveryCode(user=user, code_hash=_hash_code(c)) for c in codes
    )
    return codes


def use_recovery_code(user: User, code: str) -> bool:
    updated = MFARecoveryCode.objects.filter(
        user=user, code_hash=_hash_code(code.strip()), used_at__isnull=True
    ).update(used_at=timezone.now())
    return updated == 1


def remaining_recovery_codes(user: User) -> int:
    return user.mfa_recovery_codes.filter(used_at__isnull=True).count()


@transaction.atomic
def enable(user: User) -> list[str]:
    user.mfa_enabled = True
    user.save(update_fields=["mfa_enabled"])
    return generate_recovery_codes(user)


@transaction.atomic
def disable(user: User) -> None:
    user.mfa_enabled = False
    user.mfa_secret = ""
    user.mfa_last_used_step = 0
    user.save(update_fields=["mfa_enabled", "mfa_secret", "mfa_last_used_step"])
    user.mfa_recovery_codes.all().delete()


def make_login_token(user: User) -> str:
    """Token intermedio entre la contraseña correcta y el segundo factor."""
    return signing.dumps({"uid": str(user.pk)}, salt=LOGIN_TOKEN_SALT)


def read_login_token(token: str) -> User | None:
    try:
        data = signing.loads(token, salt=LOGIN_TOKEN_SALT, max_age=LOGIN_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return User.objects.filter(pk=data.get("uid"), is_active=True, mfa_enabled=True).first()


def verify_second_factor(user: User, code: str) -> tuple[bool, bool]:
    """Acepta un código TOTP o uno de recuperación. Devuelve (válido, fue_de_recuperación)."""
    code = code.strip().replace(" ", "")
    if verify_totp(user, code):
        return True, False
    if use_recovery_code(user, code):
        return True, True
    return False, False
