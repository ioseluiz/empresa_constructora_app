from typing import Any

from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """Agrega `code` a los errores simples ({"detail": ..., "code": ...}) para que el
    frontend pueda reaccionar a casos concretos (p. ej. `mfa_setup_required`)."""
    response = drf_exception_handler(exc, context)
    if (
        response is not None
        and isinstance(exc, APIException)
        and isinstance(response.data, dict)
        and "detail" in response.data
    ):
        codes = exc.get_codes()
        if isinstance(codes, str):
            response.data["code"] = codes
    return response
