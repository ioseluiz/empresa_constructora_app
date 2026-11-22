from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit

from .models import Tenant
from .permissions import TENANT_HEADER, IsTenantMember

TENANT_HEADER_PARAM = OpenApiParameter(
    TENANT_HEADER,
    OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Empresa activa",
)


class TenantScopedAPIView(APIView):
    """Base de toda vista de negocio: exige usuario autenticado y miembro de la empresa activa."""

    permission_classes = [IsAuthenticated, IsTenantMember]


class TenantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "legal_name",
            "slug",
            "ruc",
            "dv",
            "country",
            "currency",
            "timezone",
            "applies_cba",
            "require_mfa",
        ]
        read_only_fields = ["id", "slug", "country", "currency"]

    def validate_require_mfa(self, value: bool) -> bool:
        request = self.context.get("request")
        if value and request is not None and not request.user.mfa_enabled:
            raise serializers.ValidationError(
                "Activa primero tu propia verificación en dos pasos para no perder el acceso."
            )
        return value


@extend_schema(parameters=[TENANT_HEADER_PARAM], tags=["empresa"])
class CurrentTenantView(TenantScopedAPIView):
    def get_permissions(self) -> list:
        from apps.iam.permissions import HasTenantPermission

        return [*super().get_permissions(), HasTenantPermission()]

    @property
    def required_permission(self) -> str | None:
        return None if self.request.method in ("GET", "HEAD", "OPTIONS") else "tenant.manage"

    @extend_schema(responses=TenantSerializer)
    def get(self, request: Request) -> Response:
        return Response(TenantSerializer(request.tenant).data)  # type: ignore[attr-defined]

    @extend_schema(request=TenantSerializer, responses=TenantSerializer)
    def patch(self, request: Request) -> Response:
        serializer = TenantSerializer(
            request.tenant,  # type: ignore[attr-defined]
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        before = TenantSerializer(request.tenant).data  # type: ignore[attr-defined]
        tenant = serializer.save(updated_by=request.user)
        changes = audit.diff(dict(before), dict(serializer.data))
        if changes:
            audit.record(audit.Action.UPDATE, tenant, request=request, changes=changes)
        return Response(serializer.data)
