from typing import Any

from django.db import transaction
from django.db.models import Count, ProtectedError, Q, QuerySet
from django_filters import rest_framework as filters
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.hr.serializers import current_assignments
from apps.iam.permissions import (
    TenantPermissionMixin,
    filter_by_project_scope,
    get_request_scope,
)
from apps.iam.services import ALL_PROJECTS

from . import services
from .models import ClockCode, Device, ImportBatch, ImportRow, ImportTemplate, Punch
from .serializers import (
    ClockCodeSerializer,
    CorrectPunchSerializer,
    DeviceSerializer,
    ImportBatchSerializer,
    ImportRowPageSerializer,
    ImportRowSerializer,
    ImportTemplateSerializer,
    ManualPunchResultSerializer,
    ManualPunchSerializer,
    PunchSerializer,
    RevertSerializer,
    VoidPunchSerializer,
)
from .tasks import process_import_batch

VIEW, IMPORT, MANUAL = "timeclock.view", "timeclock.import", "timeclock.manual"
CONFIG_PERMISSIONS = {
    "create": IMPORT,
    "update": IMPORT,
    "partial_update": IMPORT,
    "destroy": IMPORT,
}


def ensure_project_scope(request: Request, permission: str, project_id: Any) -> None:
    scope = get_request_scope(request, permission)
    if scope == ALL_PROJECTS:
        return
    if project_id is None or project_id not in scope:
        raise PermissionDenied("Solo puedes operar sobre los proyectos asignados a tu rol.")


class AuditedConfigViewSet(TenantPermissionMixin, viewsets.ModelViewSet):
    """Configuración de marcaciones: lectura con timeclock.view, cambios con timeclock.import."""

    action_permissions = {**CONFIG_PERMISSIONS, "list": VIEW, "retrieve": VIEW}
    pagination_class = None

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        obj = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, obj, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        before = dict(self.get_serializer(serializer.instance).data)
        obj = serializer.save(updated_by=self.request.user)
        changes = audit.diff(before, dict(self.get_serializer(obj).data))
        if changes:
            audit.record(audit.Action.UPDATE, obj, request=self.request, changes=changes)

    def perform_destroy(self, instance: Any) -> None:
        data = dict(self.get_serializer(instance).data)
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise ValidationError(
                "No se puede eliminar porque tiene marcaciones o lotes asociados. Desactívalo."
            ) from exc
        audit.record(
            audit.Action.DELETE,
            object_type=instance._meta.label_lower,
            object_id=str(data.get("id", "")),
            object_repr=str(instance)[:255],
            request=self.request,
            changes=data,
        )


@extend_schema(tags=["marcaciones"])
class DeviceViewSet(AuditedConfigViewSet):
    serializer_class = DeviceSerializer
    filterset_fields = ["project", "is_active"]

    def get_queryset(self) -> QuerySet[Device]:
        return Device.objects.select_related("project")


@extend_schema(tags=["marcaciones"])
class ClockCodeViewSet(AuditedConfigViewSet):
    serializer_class = ClockCodeSerializer
    filterset_fields = ["employee", "device"]
    search_fields = ["code", "employee__first_name", "employee__last_name", "employee__code"]

    def get_queryset(self) -> QuerySet[ClockCode]:
        return ClockCode.objects.select_related("employee", "device")


@extend_schema(tags=["marcaciones"])
class ImportTemplateViewSet(AuditedConfigViewSet):
    serializer_class = ImportTemplateSerializer

    def get_queryset(self) -> QuerySet[ImportTemplate]:
        return ImportTemplate.objects.all()


@extend_schema(tags=["marcaciones"])
class ImportBatchViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Importación en dos pasos: subir (se procesa en segundo plano y queda en vista previa) y
    confirmar. Un lote confirmado puede revertirse: sus marcaciones se anulan, no se borran."""

    serializer_class = ImportBatchSerializer
    required_permission = IMPORT
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ["status", "source", "device", "project"]

    def get_queryset(self) -> QuerySet[ImportBatch]:
        qs = ImportBatch.objects.select_related(
            "template", "device", "project", "created_by"
        ).annotate(active_punches=Count("punches", filter=Q(punches__is_void=False)))
        if getattr(self, "swagger_fake_view", False):
            return qs
        if get_request_scope(self.request, IMPORT) == ALL_PROJECTS:
            return qs
        return qs.filter(created_by=self.request.user)

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        # Los filtros de la lista no aplican a las acciones sobre un registro.
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        data = serializer.validated_data
        device, project = data.get("device"), data.get("project")
        ensure_project_scope(
            self.request,
            IMPORT,
            (device.project_id if device else None) or (project.pk if project else None),
        )
        batch = serializer.save(created_by=self.request.user)
        tenant_id = str(self.request.tenant.pk)  # type: ignore[attr-defined]
        transaction.on_commit(lambda: process_import_batch.delay(tenant_id, str(batch.pk)))
        audit.record(
            audit.Action.CREATE,
            batch,
            request=self.request,
            changes={"archivo": batch.original_name},
        )

    @extend_schema(
        responses=ImportRowPageSerializer,
        parameters=[
            OpenApiParameter("row_status", str, enum=ImportRow.Status.values),
            OpenApiParameter("page", int),
        ],
    )
    @action(detail=True, methods=["get"])
    def rows(self, request: Request, pk: str | None = None) -> Response:
        batch = self.get_object()
        qs = self.filter_queryset_rows(batch.rows.select_related("employee", "device"))
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(ImportRowSerializer(page, many=True).data)

    def filter_queryset_rows(self, qs: QuerySet[ImportRow]) -> QuerySet[ImportRow]:
        wanted = self.request.query_params.get("row_status")
        return qs.filter(status=wanted) if wanted else qs

    def _require(self, batch: ImportBatch, *statuses: str) -> None:
        if batch.status not in statuses:
            raise ValidationError(f"El lote está en estado «{batch.get_status_display()}».")

    @extend_schema(request=None, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def confirm(self, request: Request, pk: str | None = None) -> Response:
        batch = self.get_object()
        self._require(batch, ImportBatch.Status.PREVIEW)
        scope = get_request_scope(request, IMPORT)
        if scope != ALL_PROJECTS:
            rows = batch.rows.filter(status=ImportRow.Status.VALID).select_related("device")
            if any(services.row_project(r, batch) not in scope for r in rows):
                raise PermissionDenied(
                    "El archivo incluye marcaciones de proyectos fuera de tu alcance."
                )
        created = services.confirm_batch(batch, request.user)
        audit.record(
            audit.Action.APPROVE, batch, request=request, changes={"marcaciones_creadas": created}
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=batch.pk)).data)

    @extend_schema(request=RevertSerializer, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def revert(self, request: Request, pk: str | None = None) -> Response:
        batch = self.get_object()
        self._require(batch, ImportBatch.Status.CONFIRMED)
        params = RevertSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        voided = services.revert_batch(batch, request.user, params.validated_data["reason"])
        audit.record(
            audit.Action.REVOKE,
            batch,
            request=request,
            changes={"marcaciones_anuladas": voided, "motivo": params.validated_data["reason"]},
        )
        return Response(self.get_serializer(self.get_queryset().get(pk=batch.pk)).data)

    @extend_schema(request=None, responses=ImportBatchSerializer)
    @action(detail=True, methods=["post"])
    def discard(self, request: Request, pk: str | None = None) -> Response:
        batch = self.get_object()
        self._require(batch, ImportBatch.Status.PREVIEW, ImportBatch.Status.FAILED)
        batch.status = ImportBatch.Status.DISCARDED
        batch.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(self.get_queryset().get(pk=batch.pk)).data)


class PunchFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="timestamp", lookup_expr="date__gte")
    date_to = filters.DateFilter(field_name="timestamp", lookup_expr="date__lte")
    include_void = filters.BooleanFilter(method="filter_void", label="Incluir anuladas")

    class Meta:
        model = Punch
        fields = ["employee", "project", "source", "direction", "device", "batch"]

    def filter_void(self, qs: QuerySet, name: str, value: bool) -> QuerySet:
        return qs

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        qs = super().filter_queryset(queryset)
        if not self.form.cleaned_data.get("include_void"):
            qs = qs.filter(is_void=False)
        return qs


@extend_schema(tags=["marcaciones"])
class PunchViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Las marcaciones no se editan ni se borran: se corrigen (nueva marcación enlazada) o se
    anulan con motivo."""

    serializer_class = PunchSerializer
    action_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "manual": MANUAL,
        "correct": MANUAL,
        "void": MANUAL,
    }
    filterset_class = PunchFilter
    search_fields = [
        "employee__first_name",
        "employee__last_name",
        "employee__code",
        "employee__id_number",
    ]
    ordering_fields = ["timestamp", "created_at"]
    ordering = ["-timestamp"]

    def get_queryset(self) -> QuerySet[Punch]:
        qs = Punch.objects.select_related(
            "employee", "device", "project", "created_by", "voided_by"
        )
        if getattr(self, "swagger_fake_view", False):
            return qs
        return filter_by_project_scope(qs, self.request, VIEW)

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        # Los filtros de la lista no aplican a las acciones sobre un registro.
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    @extend_schema(request=ManualPunchSerializer, responses={201: ManualPunchResultSerializer})
    @action(detail=False, methods=["post"])
    def manual(self, request: Request) -> Response:
        """Registro manual, individual o por cuadrilla (misma hora a varios empleados)."""
        params = ManualPunchSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        project = data.get("project")
        ensure_project_scope(request, MANUAL, project.pk if project else None)
        if get_request_scope(request, MANUAL) != ALL_PROJECTS:
            assigned = set(
                current_assignments().filter(project=project).values_list("employee_id", flat=True)
            )
            foreign = [e.full_name for e in data["employees"] if e.pk not in assigned]
            if foreign:
                raise ValidationError(
                    {"employees": f"No están asignados a {project.code}: {', '.join(foreign[:5])}."}
                )
        created, skipped = services.create_manual_punches(
            employees=data["employees"],
            timestamp=data["timestamp"],
            direction=data["direction"],
            project=project,
            reason=data["reason"],
            user=request.user,
        )
        for punch in created:
            audit.record(
                audit.Action.CREATE, punch, request=request, changes={"motivo": punch.reason}
            )
        body = {
            "created": PunchSerializer(created, many=True).data,
            "skipped": [e.full_name for e in skipped],
        }
        return Response(body, status=status.HTTP_201_CREATED)

    def _get_active(self) -> Punch:
        punch = self.get_object()
        if punch.is_void:
            raise ValidationError("La marcación ya está anulada.")
        ensure_project_scope(self.request, MANUAL, punch.project_id)
        return punch

    @extend_schema(request=CorrectPunchSerializer, responses={201: PunchSerializer})
    @action(detail=True, methods=["post"])
    def correct(self, request: Request, pk: str | None = None) -> Response:
        punch = self._get_active()
        params = CorrectPunchSerializer(data=request.data, context={"punch": punch})
        params.is_valid(raise_exception=True)
        new = services.correct_punch(punch, user=request.user, **params.validated_data)
        audit.record(
            audit.Action.UPDATE,
            punch,
            request=request,
            changes={
                "timestamp": {"antes": punch.timestamp, "despues": new.timestamp},
                "direction": {"antes": punch.direction, "despues": new.direction},
                "motivo": new.reason,
            },
        )
        return Response(PunchSerializer(new).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=VoidPunchSerializer, responses=PunchSerializer)
    @action(detail=True, methods=["post"])
    def void(self, request: Request, pk: str | None = None) -> Response:
        punch = self._get_active()
        params = VoidPunchSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        services.void_punches(
            Punch.objects.filter(pk=punch.pk), request.user, params.validated_data["reason"]
        )
        audit.record(
            audit.Action.REVOKE,
            punch,
            request=request,
            changes={"motivo": params.validated_data["reason"]},
        )
        return Response(PunchSerializer(self.get_queryset().get(pk=punch.pk)).data)
