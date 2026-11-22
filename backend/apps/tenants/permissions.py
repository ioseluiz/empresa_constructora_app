import uuid

from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.core.tenancy import activate_tenant

from .models import Membership

TENANT_HEADER = "X-Tenant-ID"


class IsTenantMember(BasePermission):
    """Resuelve la empresa del encabezado `X-Tenant-ID`, verifica que el usuario sea miembro
    activo y la activa (aplicación + RLS). Deja `request.tenant` y `request.membership`."""

    message = "No tienes acceso a esta empresa o no se indicó la empresa activa."

    def has_permission(self, request: Request, view: APIView) -> bool:
        raw = request.headers.get(TENANT_HEADER)
        if not raw or not request.user or not request.user.is_authenticated:
            return False
        try:
            tenant_id = uuid.UUID(raw)
        except ValueError:
            return False
        membership = (
            Membership.objects.select_related("tenant")
            .filter(user=request.user, tenant_id=tenant_id, is_active=True, tenant__is_active=True)
            .first()
        )
        if membership is None:
            return False
        if membership.tenant.require_mfa and not request.user.mfa_enabled:
            raise PermissionDenied(
                "Esta empresa exige verificación en dos pasos. Actívala en tu cuenta.",
                code="mfa_setup_required",
            )
        request.tenant = membership.tenant  # type: ignore[attr-defined]
        request.membership = membership  # type: ignore[attr-defined]
        activate_tenant(membership.tenant)
        return True
