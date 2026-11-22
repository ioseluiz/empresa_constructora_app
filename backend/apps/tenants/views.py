from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Tenant
from .permissions import TENANT_HEADER, IsTenantMember, IsTenantOwner

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
        ]
        read_only_fields = ["id", "slug", "country", "currency"]


@extend_schema(parameters=[TENANT_HEADER_PARAM], tags=["empresa"])
class CurrentTenantView(TenantScopedAPIView):
    def get_permissions(self) -> list:
        perms = list(super().get_permissions())
        if self.request.method not in ("GET", "HEAD", "OPTIONS"):
            perms.append(IsTenantOwner())
        return perms

    @extend_schema(responses=TenantSerializer)
    def get(self, request: Request) -> Response:
        return Response(TenantSerializer(request.tenant).data)  # type: ignore[attr-defined]

    @extend_schema(request=TenantSerializer, responses=TenantSerializer)
    def patch(self, request: Request) -> Response:
        serializer = TenantSerializer(request.tenant, data=request.data, partial=True)  # type: ignore[attr-defined]
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
