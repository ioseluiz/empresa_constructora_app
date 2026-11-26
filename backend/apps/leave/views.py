from typing import Any

from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.hr.models import Employee
from apps.hr.views import scope_employees
from apps.iam.permissions import TenantPermissionMixin, get_request_scope
from apps.iam.services import ALL_PROJECTS

from .models import VacationAdjustment, VacationRequest
from .serializers import (
    BalanceSerializer,
    DecisionSerializer,
    VacationAdjustmentSerializer,
    VacationRequestSerializer,
)
from .services import balance

VIEW, MANAGE, APPROVE = "leave.view", "leave.manage", "leave.approve"


def ensure_employee_scope(request: Request, permission: str, employee: Employee) -> None:
    if get_request_scope(request, permission) == ALL_PROJECTS:
        return
    if not scope_employees(Employee.objects.filter(pk=employee.pk), request, permission).exists():
        raise PermissionDenied("El empleado no pertenece a tus proyectos.")


@extend_schema(tags=["vacaciones"])
class VacationRequestViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = VacationRequestSerializer
    action_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": MANAGE,
        "update": MANAGE,
        "partial_update": MANAGE,
        "approve": APPROVE,
        "reject": APPROVE,
        "cancel": MANAGE,
    }
    filterset_fields = ["employee", "status", "payment_mode"]
    search_fields = ["employee__first_name", "employee__last_name", "employee__code"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self) -> QuerySet[VacationRequest]:
        qs = VacationRequest.objects.select_related(
            "employee", "decided_by", "paid_line__run"
        ).order_by("-start_date")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "employee__")

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        ensure_employee_scope(self.request, MANAGE, serializer.validated_data["employee"])
        obj = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, obj, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        obj: VacationRequest = serializer.instance  # type: ignore[assignment]
        if obj.status != VacationRequest.Status.REQUESTED:
            raise ValidationError({"detail": "Solo se editan solicitudes pendientes."})
        ensure_employee_scope(self.request, MANAGE, obj.employee)
        before = dict(self.get_serializer(obj).data)
        obj = serializer.save(updated_by=self.request.user)
        changes = audit.diff(before, dict(self.get_serializer(obj).data))
        if changes:
            audit.record(audit.Action.UPDATE, obj, request=self.request, changes=changes)

    def _decide(self, request: Request, status: str, permission: str) -> Response:
        obj = self.get_object()
        ensure_employee_scope(request, permission, obj.employee)
        params = DecisionSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        reason = params.validated_data.get("reason", "")
        with transaction.atomic():
            obj = VacationRequest.objects.select_for_update().get(pk=obj.pk)
            if status == VacationRequest.Status.CANCELLED:
                if obj.status not in (
                    VacationRequest.Status.REQUESTED,
                    VacationRequest.Status.APPROVED,
                ):
                    raise ValidationError({"detail": "Estas vacaciones ya no se pueden cancelar."})
                if obj.is_paid:
                    raise ValidationError(
                        {"detail": "Las vacaciones ya se pagaron: no se cancelan."}
                    )
            elif obj.status != VacationRequest.Status.REQUESTED:
                raise ValidationError({"detail": "La solicitud ya fue decidida."})
            if status == VacationRequest.Status.APPROVED:
                available = balance(obj.employee, obj.start_date).available
                if obj.days > available:
                    raise ValidationError(
                        {
                            "detail": f"Solicita {obj.days} días y el saldo disponible al "
                            f"{obj.start_date:%d/%m/%Y} es {available}. Ajusta el saldo o los días."
                        }
                    )
            if status == VacationRequest.Status.REJECTED and not reason:
                raise ValidationError({"reason": "Indica el motivo del rechazo."})
            obj.status = status
            obj.decided_at, obj.decided_by = timezone.now(), request.user
            obj.reject_reason = reason if status != VacationRequest.Status.APPROVED else ""
            obj.save()
        action_map: dict[str, str] = {
            VacationRequest.Status.APPROVED: audit.Action.APPROVE,
            VacationRequest.Status.REJECTED: audit.Action.REVOKE,
            VacationRequest.Status.CANCELLED: audit.Action.REVOKE,
        }
        audit.record(
            action_map[status], obj, request=request, changes={"estado": status, "motivo": reason}
        )
        if status != VacationRequest.Status.REQUESTED:
            self._recalculate_workdays(obj)
        return Response(self.get_serializer(obj).data)

    @staticmethod
    def _recalculate_workdays(obj: VacationRequest) -> None:
        """Las jornadas del período dejan (o vuelven) a marcar ausencia."""
        from apps.timeclock.workdays import calculate

        calculate([obj.employee], obj.start_date, obj.end_date)

    @extend_schema(request=DecisionSerializer, responses=VacationRequestSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        return self._decide(request, VacationRequest.Status.APPROVED, APPROVE)

    @extend_schema(request=DecisionSerializer, responses=VacationRequestSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request: Request, pk: str | None = None) -> Response:
        return self._decide(request, VacationRequest.Status.REJECTED, APPROVE)

    @extend_schema(request=DecisionSerializer, responses=VacationRequestSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._decide(request, VacationRequest.Status.CANCELLED, MANAGE)


@extend_schema(tags=["vacaciones"])
class VacationAdjustmentViewSet(
    TenantPermissionMixin, mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet
):
    serializer_class = VacationAdjustmentSerializer
    action_permissions = {"list": VIEW, "create": MANAGE}
    filterset_fields = ["employee"]
    pagination_class = None

    def get_queryset(self) -> QuerySet[VacationAdjustment]:
        qs = VacationAdjustment.objects.select_related("employee", "created_by")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "employee__")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        ensure_employee_scope(self.request, MANAGE, serializer.validated_data["employee"])
        obj = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, obj, request=self.request, changes=serializer.data)


@extend_schema(tags=["vacaciones"])
class BalanceViewSet(TenantPermissionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Saldo de vacaciones de los empleados activos."""

    serializer_class = BalanceSerializer
    required_permission = VIEW
    filter_backends: list[Any] = []

    def get_queryset(self) -> QuerySet[Employee]:
        qs = Employee.objects.filter(status="active").order_by("last_name", "first_name")
        if getattr(self, "swagger_fake_view", False):
            return qs
        term = self.request.query_params.get("search")
        if term:
            qs = qs.filter(
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(code__icontains=term)
            )
        return scope_employees(qs, self.request, VIEW)

    @extend_schema(parameters=[OpenApiParameter("search", str), OpenApiParameter("page", int)])
    def list(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        page = self.paginate_queryset(self.get_queryset())
        rows = []
        for e in page or []:
            b = balance(e)
            rows.append(
                {
                    "employee": e.pk,
                    "employee_code": e.code,
                    "employee_name": e.full_name,
                    "hire_date": e.hire_date,
                    **b.__dict__,
                }
            )
        return self.get_paginated_response(BalanceSerializer(rows, many=True).data)
