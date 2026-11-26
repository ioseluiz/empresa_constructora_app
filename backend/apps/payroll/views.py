from typing import Any

from django.db import transaction
from django.db.models import ProtectedError, QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit import services as audit
from apps.hr.views import scope_employees
from apps.iam.permissions import TenantPermissionMixin, get_request_scope
from apps.iam.services import ALL_PROJECTS
from apps.organization.models import CostCenter

from .calculator import PayrollInputError, calculate
from .models import LegalParameter, PayrollConcept, PayrollSettings, RecurringDeduction
from .params import MissingParameter
from .serializers import (
    LegalParameterSerializer,
    PayrollConceptSerializer,
    PayrollSettingsSerializer,
    PreviewRequestSerializer,
    PreviewResultSerializer,
    RecurringDeductionSerializer,
)
from .services import settings_for_tenant

VIEW, CONFIG, CALCULATE = "payroll.view", "payroll.config", "payroll.calculate"


@extend_schema(tags=["planilla"])
class LegalParameterViewSet(TenantPermissionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Parámetros legales vigentes y su historial (los administra la plataforma)."""

    serializer_class = LegalParameterSerializer
    required_permission = VIEW
    pagination_class = None
    filterset_fields = ["country", "key"]

    def get_queryset(self) -> QuerySet[LegalParameter]:
        return LegalParameter.objects.all()


@extend_schema(tags=["planilla"])
class PayrollSettingsView(TenantPermissionMixin, RetrieveUpdateAPIView):
    serializer_class = PayrollSettingsSerializer
    required_permission = VIEW  # además, la escritura exige payroll.config (check_permissions)
    http_method_names = ["get", "patch"]

    def get_object(self) -> PayrollSettings:
        return settings_for_tenant()

    def check_permissions(self, request: Request) -> None:
        super().check_permissions(request)
        if request.method == "PATCH":
            from apps.iam.permissions import get_request_permissions

            if CONFIG not in get_request_permissions(request):
                raise PermissionDenied("Necesitas el permiso de configuración de planilla.")

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        before = dict(PayrollSettingsSerializer(serializer.instance).data)
        obj = serializer.save(updated_by=self.request.user)
        changes = audit.diff(before, dict(PayrollSettingsSerializer(obj).data))
        if changes:
            audit.record(audit.Action.UPDATE, obj, request=self.request, changes=changes)


class AuditedPayrollViewSet(TenantPermissionMixin, viewsets.ModelViewSet):
    action_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "create": CONFIG,
        "update": CONFIG,
        "partial_update": CONFIG,
        "destroy": CONFIG,
    }
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


@extend_schema(tags=["planilla"])
class PayrollConceptViewSet(AuditedPayrollViewSet):
    serializer_class = PayrollConceptSerializer
    filterset_fields = ["kind", "is_active"]

    def get_queryset(self) -> QuerySet[PayrollConcept]:
        return PayrollConcept.objects.all()

    def perform_destroy(self, instance: PayrollConcept) -> None:
        if instance.is_system:
            raise ValidationError("Los conceptos del sistema no se eliminan: puedes desactivarlos.")
        try:
            with transaction.atomic():
                instance.delete()
        except ProtectedError as exc:
            raise ValidationError("El concepto está en uso. Desactívalo.") from exc


@extend_schema(tags=["planilla"])
class RecurringDeductionViewSet(AuditedPayrollViewSet):
    serializer_class = RecurringDeductionSerializer
    filterset_fields = ["employee", "concept", "is_active"]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self) -> QuerySet[RecurringDeduction]:
        qs = RecurringDeduction.objects.select_related("employee", "concept")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "employee__")


@extend_schema(tags=["planilla"])
class PreviewView(TenantPermissionMixin, APIView):
    """Simula la planilla de un empleado en un período, con el detalle de cada concepto.
    No guarda nada."""

    required_permission = CALCULATE

    @extend_schema(request=PreviewRequestSerializer, responses=PreviewResultSerializer)
    def post(self, request: Request) -> Response:
        params = PreviewRequestSerializer(data=request.data)
        params.is_valid(raise_exception=True)
        employee = params.validated_data["employee"]
        if (
            get_request_scope(request, CALCULATE) != ALL_PROJECTS
            and not scope_employees(
                employee.__class__.objects.filter(pk=employee.pk), request, CALCULATE
            ).exists()
        ):
            raise PermissionDenied("El empleado no pertenece a tus proyectos.")
        try:
            result = calculate(
                employee,
                params.validated_data["period_start"],
                params.validated_data["period_end"],
                params.validated_data.get("pay_date"),
            )
        except (PayrollInputError, MissingParameter, LookupError) as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        codes = dict(CostCenter.objects.values_list("pk", "code"))
        body: dict[str, Any] = {
            "lines": [
                {
                    "code": ln.code,
                    "name": ln.name,
                    "kind": ln.kind,
                    "amount": ln.amount,
                    "quantity": ln.quantity,
                    "rate": ln.rate,
                    "cost_center": codes.get(ln.cost_center_id),
                    "detail": ln.detail,
                }
                for ln in result.lines
            ],
            "gross": result.gross,
            "deductions": result.deductions,
            "net": result.net,
            "employer_cost": result.employer_cost,
            "warnings": result.warnings,
            "explanation": result.explanation,
            "parameters": result.parameters,
        }
        return Response(PreviewResultSerializer(body).data)
