from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from .tenancy import deactivate_tenant


class TenantContextMiddleware:
    """Garantiza que el tenant de una petición nunca se filtre a la siguiente
    (los workers reutilizan hilos)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        deactivate_tenant()
        try:
            return self.get_response(request)
        finally:
            deactivate_tenant()
