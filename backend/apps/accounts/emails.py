from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User


def send_password_reset_email(user: User) -> None:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/restablecer-contrasena?uid={uid}&token={token}"
    body = (
        f"Hola {user.full_name},\n\n"
        "Recibimos una solicitud para restablecer tu contraseña. "
        f"Usa este enlace (válido por {settings.PASSWORD_RESET_TIMEOUT // 3600} horas):\n\n"
        f"{link}\n\n"
        "Si no fuiste tú, ignora este correo; tu contraseña no cambiará.\n"
    )
    send_mail(
        subject="Restablecer contraseña",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )
