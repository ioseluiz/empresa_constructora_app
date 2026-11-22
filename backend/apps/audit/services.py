"""API única para registrar auditoría desde los servicios y vistas de negocio."""

from typing import Any

from django.conf import settings
from django.db import models
from rest_framework.request import Request

from apps.core.tenancy import require_current_tenant

from .models import AuditLog

Action = AuditLog.Action


def client_ip(request: Request | None) -> str | None:
    """IP del cliente. `X-Forwarded-For` solo es confiable para los saltos agregados por
    nuestros propios proxies (NUM_PROXIES, p. ej. 1 detrás del balanceador): los valores a la
    izquierda los puede inventar el cliente."""
    if request is None:
        return None
    proxies = settings.NUM_PROXIES
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if proxies and forwarded:
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if len(hops) >= proxies:
            return hops[-proxies]
    return request.META.get("REMOTE_ADDR")


def _jsonable(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if isinstance(value, list | tuple | set):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return str(value)


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Solo los campos que cambiaron: {"campo": {"antes": x, "despues": y}}."""
    return {
        key: {"antes": _jsonable(before.get(key)), "despues": _jsonable(after.get(key))}
        for key in sorted(set(before) | set(after))
        if before.get(key) != after.get(key)
    }


def record(
    action: str,
    obj: models.Model | None = None,
    *,
    request: Request | None = None,
    object_type: str | None = None,
    object_id: str = "",
    object_repr: str = "",
    changes: dict[str, Any] | None = None,
    actor: Any = None,
) -> AuditLog:
    """Registra un evento. `actor` por defecto es el usuario autenticado de la petición
    (indíquelo explícitamente en endpoints públicos, p. ej. al aceptar una invitación)."""
    if actor is None:
        user = getattr(request, "user", None) if request is not None else None
        actor = user if user is not None and user.is_authenticated else None
    if obj is not None:
        object_type = object_type or obj._meta.label_lower
        object_id = object_id or str(obj.pk)
        object_repr = object_repr or str(obj)[:255]
    return AuditLog.objects.create(
        tenant=require_current_tenant(),
        actor=actor,
        actor_email=getattr(actor, "email", "") or "",
        action=action,
        object_type=object_type or "",
        object_id=object_id,
        object_repr=object_repr,
        changes=_jsonable(changes or {}),
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request else "")[:255],
    )
