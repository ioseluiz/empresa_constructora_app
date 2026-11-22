from django.db import transaction
from django.db.models import ProtectedError, QuerySet
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.iam.permissions import TenantPermissionMixin

from .models import CBACategory, CBAWageRate, CostCenter, Holiday, Position
from .serializers import (
    CBACategorySerializer,
    CBAWageRateSerializer,
    CostCenterSerializer,
    GenerateHolidaysSerializer,
    HolidaySerializer,
    PositionSerializer,
)
from .services import generate_holidays

# Lectura: cualquier miembro (otros módulos usan estos catálogos). Escritura: org.manage.
CATALOG_PERMISSIONS = {
    "create": "org.manage",
    "update": "org.manage",
    "partial_update": "org.manage",
    "destroy": "org.manage",
    "generate": "org.manage",
}


class AuditedCatalogViewSet(TenantPermissionMixin, viewsets.ModelViewSet):
    """CRUD de catálogo con auditoría y borrado protegido."""

    action_permissions = CATALOG_PERMISSIONS
    pagination_class = None
    serializer_class: type[serializers.ModelSerializer]

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        obj = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, obj, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        before = dict(self.get_serializer(serializer.instance).data)
        obj = serializer.save(updated_by=self.request.user)
        changes = audit.diff(before, dict(self.get_serializer(obj).data))
        if changes:
            audit.record(audit.Action.UPDATE, obj, request=self.request, changes=changes)

    def perform_destroy(self, instance) -> None:
        label, pk, object_type = str(instance), str(instance.pk), instance._meta.label_lower
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                "No se puede eliminar porque está en uso. Puedes desactivarlo."
            ) from exc
        audit.record(
            audit.Action.DELETE,
            request=self.request,
            object_type=object_type,
            object_id=pk,
            object_repr=label,
        )


@extend_schema(tags=["organizacion"])
class CostCenterViewSet(AuditedCatalogViewSet):
    serializer_class = CostCenterSerializer
    filterset_fields = ["kind", "is_active", "parent"]
    search_fields = ["code", "name"]

    def get_queryset(self) -> QuerySet[CostCenter]:
        return CostCenter.objects.select_related("project").order_by("code")

    def perform_destroy(self, instance: CostCenter) -> None:
        if instance.kind != CostCenter.Kind.AREA:
            raise ValidationError("Solo se pueden eliminar centros de costo de tipo área.")
        super().perform_destroy(instance)


@extend_schema(tags=["organizacion"])
class PositionViewSet(AuditedCatalogViewSet):
    serializer_class = PositionSerializer
    filterset_fields = ["area", "is_active", "cba_category"]
    search_fields = ["code", "name"]

    def get_queryset(self) -> QuerySet[Position]:
        return Position.objects.select_related("cba_category")


@extend_schema(tags=["organizacion"])
class CBACategoryViewSet(AuditedCatalogViewSet):
    serializer_class = CBACategorySerializer
    filterset_fields = ["is_active"]
    search_fields = ["code", "name"]

    def get_queryset(self) -> QuerySet[CBACategory]:
        return CBACategory.objects.prefetch_related("rates")


@extend_schema(tags=["organizacion"])
class CBAWageRateViewSet(AuditedCatalogViewSet):
    serializer_class = CBAWageRateSerializer
    filterset_fields = ["category"]

    def get_queryset(self) -> QuerySet[CBAWageRate]:
        return CBAWageRate.objects.select_related("category")


@extend_schema_view(
    list=extend_schema(parameters=[OpenApiParameter("year", int, description="Año")])
)
@extend_schema(tags=["organizacion"])
class HolidayViewSet(AuditedCatalogViewSet):
    serializer_class = HolidaySerializer
    filterset_fields = ["kind"]

    def get_queryset(self) -> QuerySet[Holiday]:
        qs = Holiday.objects.all()
        year = self.request.query_params.get("year")
        if year and year.isdigit():
            qs = qs.filter(date__year=int(year))
        return qs

    @extend_schema(request=GenerateHolidaysSerializer, responses=HolidaySerializer(many=True))
    @action(detail=False, methods=["post"])
    def generate(self, request: Request) -> Response:
        """Carga los feriados nacionales de Panamá del año indicado (no duplica)."""
        data = GenerateHolidaysSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        created = generate_holidays(data.validated_data["year"])
        if created:
            audit.record(
                audit.Action.CREATE,
                request=request,
                object_type="organization.holiday",
                object_repr=f"Feriados nacionales {data.validated_data['year']}",
                changes={"creados": [str(h) for h in created]},
            )
        return Response(HolidaySerializer(created, many=True).data, status=status.HTTP_201_CREATED)
