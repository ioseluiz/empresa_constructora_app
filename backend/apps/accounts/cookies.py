"""El refresh token viaja solo en una cookie httpOnly; el access token vive en memoria del
navegador. Así un XSS no puede robar la sesión de larga duración."""

from django.conf import settings
from rest_framework.response import Response

REFRESH_COOKIE = "refresh_token"


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite="Lax",
        path=settings.AUTH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=settings.AUTH_COOKIE_PATH, samesite="Lax")
