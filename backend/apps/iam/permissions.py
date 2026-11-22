from typing import Any

from django.db.models import QuerySet
from rest_framework.permissions import SAFE_METHODS, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.tenants.permissions import IsTenantMember

from .services import ALL_PROJECTS, Scope, effective_permissions, permission_scope


def get_request_permissions(request: Request) -> set[str]:
    cached = getattr(request, "_tenant_permissions", None)
    if cached is None:
        cached = effective_permissions(request.membership)  # type: ignore[attr-defined]
        request._tenant_permissions = cached  # type: ignore[attr-defined]
    return cached


def get_request_scope(request: Request, permission: str) -> Scope:
    cache: dict[str, Scope] = request.__dict__.setdefault("_tenant_scopes", {})
    if permission not in cache:
        cache[permission] = permission_scope(request.membership, permission)  # type: ignore[attr-defined]
    return cache[permission]


def filter_by_project_scope(
    queryset: QuerySet, request: Request, permission: str, project_field: str = "project"
) -> QuerySet:
    """Restringe un queryset a los proyectos donde el usuario tiene `permission`.
    `project_field` es la ruta al proyecto (p. ej. "pk" para Project, "project" para modelos
    relacionados)."""
    scope = get_request_scope(request, permission)
    if scope == ALL_PROJECTS:
        return queryset
    return queryset.filter(**{f"{project_field}__in": scope})


class HasTenantPermission(BasePermission):
    """Exige el permiso que declara la vista, en este orden:

    - `action_permissions = {"create": "users.manage", ...}` (viewsets, por acción)
    - `required_permission = "audit.view"` (uno para toda la vista)
    - `permission_resource = "users"` → `users.view` en lectura, `users.manage` en escritura
    """

    message = "No tienes permiso para realizar esta acción."

    @staticmethod
    def required_for(request: Request, view: APIView) -> str | None:
        action = getattr(view, "action", None)
        mapping: dict[str, str] = getattr(view, "action_permissions", {})
        if action and action in mapping:
            return mapping[action]
        if getattr(view, "required_permission", None):
            return view.required_permission  # type: ignore[attr-defined]
        resource = getattr(view, "permission_resource", None)
        if resource:
            return f"{resource}.view" if request.method in SAFE_METHODS else f"{resource}.manage"
        return None

    def has_permission(self, request: Request, view: APIView) -> bool:
        required = self.required_for(request, view)
        return required is None or required in get_request_permissions(request)


class TenantPermissionMixin:
    """Mezclar en toda vista de negocio: usuario autenticado + miembro de la empresa activa +
    permiso requerido."""

    permission_classes: Any = [IsAuthenticated, IsTenantMember, HasTenantPermission]
