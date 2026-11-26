from datetime import date
from typing import Any

from django.db import transaction
from django.db.models import Count, ProtectedError, Q, QuerySet
from django.http import FileResponse, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
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

from . import payslips, reports, runs
from .calculator import PayrollInputError, calculate
from .models import (
    LegalParameter,
    PayrollConcept,
    PayrollRun,
    PayrollSettings,
    Payslip,
    RecurringDeduction,
)
from .params import MissingParameter
from .serializers import (
    AchSummarySerializer,
    ConsolidatedSerializer,
    EmailResultSerializer,
    LegalParameterSerializer,
    PayrollConceptSerializer,
    PayrollLineSerializer,
    PayrollRunSerializer,
    PayrollSettingsSerializer,
    PayslipSerializer,
    PreviewRequestSerializer,
    PreviewResultSerializer,
    RecurringDeductionSerializer,
)
from .services import settings_for_tenant
from .tasks import generate_payslips

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


# ------------------------------------------------------------------ Sprint 9: corridas

APPROVE = "payroll.approve"
REPORTS = "payroll.reports"


def attachment(content: bytes, filename: str, content_type: str) -> HttpResponse:
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


def ensure_run_scope(request: Request, permission: str, run_scope: str, project_id: Any) -> None:
    scope = get_request_scope(request, permission)
    if scope == ALL_PROJECTS:
        return
    if run_scope != PayrollRun.Scope.PROJECT or project_id not in scope:
        raise PermissionDenied("Solo puedes operar planillas de los proyectos asignados a tu rol.")


@extend_schema(tags=["planilla"])
class PayrollRunViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Corridas de planilla: borrador → calculada → aprobada → pagada (o anulada antes de
    aprobar). Una planilla aprobada no cambia."""

    serializer_class = PayrollRunSerializer
    action_permissions = {
        "list": VIEW,
        "retrieve": VIEW,
        "lines": VIEW,
        "summary": VIEW,
        "create": CALCULATE,
        "calculate": CALCULATE,
        "cancel": CALCULATE,
        "approve": APPROVE,
        "pay": APPROVE,
        "payslips": VIEW,
        "generate_payslips": APPROVE,
        "payslips_zip": VIEW,
        "email_payslips": REPORTS,
        "ach": REPORTS,
        "ach_file": REPORTS,
    }
    filterset_fields = ["status", "scope", "project", "frequency"]
    ordering = ["-period_end", "-number"]

    def get_queryset(self) -> QuerySet[PayrollRun]:
        qs = PayrollRun.objects.select_related("project", "calculated_by", "approved_by").annotate(
            error_count=Count("lines", filter=~Q(lines__error="")),
            warning_count=Count("lines", filter=~Q(lines__warnings=[])),
        )
        if getattr(self, "swagger_fake_view", False):
            return qs
        scope = get_request_scope(self.request, VIEW)
        if scope == ALL_PROJECTS:
            return qs
        return qs.filter(scope=PayrollRun.Scope.PROJECT, project_id__in=scope)

    def filter_queryset(self, queryset: QuerySet) -> QuerySet:
        return super().filter_queryset(queryset) if self.action == "list" else queryset

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        data = serializer.validated_data
        project = data.get("project")
        ensure_run_scope(self.request, CALCULATE, data["scope"], project.pk if project else None)
        run = runs.create_run(**data, created_by=self.request.user)
        serializer.instance = run
        audit.record(audit.Action.CREATE, run, request=self.request, changes=serializer.data)

    def _act(self, request: Request, permission: str, fn: Any, action: str) -> Response:
        run = self.get_object()
        ensure_run_scope(request, permission, run.scope, run.project_id)
        try:
            run = fn(run, request.user)
        except runs.RunError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        audit.record(action, run, request=request, changes={"estado": run.status})
        return Response(self.get_serializer(self.get_queryset().get(pk=run.pk)).data)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def calculate(self, request: Request, pk: str | None = None) -> Response:
        return self._act(request, CALCULATE, runs.calculate_run, audit.Action.UPDATE)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request: Request, pk: str | None = None) -> Response:
        response = self._act(request, APPROVE, runs.approve_run, audit.Action.APPROVE)
        tenant_id, run_id = str(request.tenant.pk), str(response.data["id"])  # type: ignore[attr-defined]
        transaction.on_commit(lambda: generate_payslips.delay(tenant_id, run_id))
        return response

    # ---------------------------------------------------------------- comprobantes y archivos

    @extend_schema(responses=PayslipSerializer(many=True))
    @action(detail=True, methods=["get"], pagination_class=None)
    def payslips(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        qs = run.payslips.select_related("employee", "run").order_by("number")
        return Response(PayslipSerializer(qs, many=True).data)

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"], url_path="payslips/generate")
    def generate_payslips(self, request: Request, pk: str | None = None) -> Response:
        """Emite los comprobantes que falten (si la generación automática no terminó)."""
        run = self.get_object()
        ensure_run_scope(request, APPROVE, run.scope, run.project_id)
        try:
            created = payslips.generate_for_run(run)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response({"created": created})

    @extend_schema(responses={(200, "application/zip"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="payslips/zip")
    def payslips_zip(self, request: Request, pk: str | None = None) -> HttpResponse:
        run = self.get_object()
        if not run.payslips.exists():
            raise ValidationError({"detail": "La planilla aún no tiene comprobantes."})
        audit.record(audit.Action.EXPORT, run, request=request, changes={"comprobantes": "zip"})
        return attachment(
            payslips.zip_for_run(run), f"comprobantes_planilla_{run.number}.zip", "application/zip"
        )

    @extend_schema(request=None, responses=EmailResultSerializer)
    @action(detail=True, methods=["post"], url_path="payslips/email")
    def email_payslips(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        ensure_run_scope(request, REPORTS, run.scope, run.project_id)
        result = payslips.email_payslips(list(run.payslips.select_related("employee", "run")))
        audit.record(audit.Action.EXPORT, run, request=request, changes={"correos": result["sent"]})
        return Response(result)

    @extend_schema(responses=AchSummarySerializer)
    @action(detail=True, methods=["get"], url_path="ach")
    def ach(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        return Response(AchSummarySerializer(reports.ach_summary(run).__dict__).data)

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"], url_path="ach/file")
    def ach_file(self, request: Request, pk: str | None = None) -> HttpResponse:
        run = self.get_object()
        ensure_run_scope(request, REPORTS, run.scope, run.project_id)
        if run.status not in (PayrollRun.Status.APPROVED, PayrollRun.Status.PAID):
            raise ValidationError(
                {"detail": "El archivo de pago se genera con la planilla aprobada."}
            )
        try:
            name, content = reports.ach_file(run)
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        audit.record(audit.Action.EXPORT, run, request=request, changes={"archivo": name})
        return attachment(content, name, "text/csv; charset=utf-8")

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def pay(self, request: Request, pk: str | None = None) -> Response:
        return self._act(request, APPROVE, runs.mark_paid, audit.Action.UPDATE)

    @extend_schema(request=None, responses=PayrollRunSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk: str | None = None) -> Response:
        return self._act(request, CALCULATE, runs.cancel_run, audit.Action.REVOKE)

    @extend_schema(
        responses=PayrollLineSerializer(many=True),
        parameters=[OpenApiParameter("search", str), OpenApiParameter("page", int)],
    )
    @action(detail=True, methods=["get"])
    def lines(self, request: Request, pk: str | None = None) -> Response:
        run = self.get_object()
        qs = run.lines.select_related("employee").prefetch_related("items__cost_center")
        term = request.query_params.get("search")
        if term:
            qs = qs.filter(
                Q(employee__first_name__icontains=term)
                | Q(employee__last_name__icontains=term)
                | Q(employee__code__icontains=term)
            )
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(PayrollLineSerializer(page, many=True).data)

    @extend_schema(responses=ConsolidatedSerializer)
    @action(detail=True, methods=["get"])
    def summary(self, request: Request, pk: str | None = None) -> Response:
        return Response(ConsolidatedSerializer(runs.consolidated([self.get_object()])).data)


@extend_schema(tags=["planilla"])
class ConsolidatedView(TenantPermissionMixin, APIView):
    """Planilla global: consolida las corridas con fecha de pago en el rango."""

    required_permission = VIEW

    @extend_schema(
        parameters=[
            OpenApiParameter("date_from", OpenApiTypes.DATE, required=True),
            OpenApiParameter("date_to", OpenApiTypes.DATE, required=True),
            OpenApiParameter("include_calculated", OpenApiTypes.BOOL),
        ],
        responses=ConsolidatedSerializer,
    )
    def get(self, request: Request) -> Response:
        if get_request_scope(request, VIEW) != ALL_PROJECTS:
            raise PermissionDenied("La planilla global requiere acceso a toda la empresa.")
        try:
            start = date.fromisoformat(request.query_params["date_from"])
            end = date.fromisoformat(request.query_params["date_to"])
        except (KeyError, ValueError) as exc:
            raise ValidationError({"detail": "Indica date_from y date_to (AAAA-MM-DD)."}) from exc
        include = request.query_params.get("include_calculated") in ("true", "1")
        selected = runs.runs_paid_between(start, end, include)
        return Response(ConsolidatedSerializer(runs.consolidated(selected)).data)


@extend_schema(tags=["planilla"])
class PayslipViewSet(TenantPermissionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Comprobantes emitidos (p. ej. los de un empleado en su expediente)."""

    serializer_class = PayslipSerializer
    required_permission = VIEW
    filterset_fields = ["employee", "run"]

    def get_queryset(self) -> QuerySet[Payslip]:
        qs = Payslip.objects.select_related("employee", "run")
        if getattr(self, "swagger_fake_view", False):
            return qs
        scope = get_request_scope(self.request, VIEW)
        if scope == ALL_PROJECTS:
            return qs
        return qs.filter(run__scope=PayrollRun.Scope.PROJECT, run__project_id__in=scope)

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        slip = self.get_object()
        audit.record(audit.Action.EXPORT, slip, request=request, changes={"descarga": slip.number})
        response = FileResponse(
            slip.pdf.open("rb"),
            as_attachment=True,
            filename=f"comprobante_{slip.number:07d}_{slip.employee.code}.pdf",
            content_type="application/pdf",
        )
        response["Cache-Control"] = "private, no-store"
        return response


@extend_schema(tags=["planilla"])
class SipeReportView(TenantPermissionMixin, APIView):
    """Informe mensual de cuotas de Seguro Social y Seguro Educativo (Excel)."""

    required_permission = REPORTS

    @extend_schema(
        parameters=[OpenApiParameter("month", str, required=True, description="AAAA-MM")],
        responses={
            (
                200,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ): OpenApiTypes.BINARY
        },
    )
    def get(self, request: Request) -> HttpResponse:
        if get_request_scope(request, REPORTS) != ALL_PROJECTS:
            raise PermissionDenied("El informe de la CSS requiere acceso a toda la empresa.")
        try:
            year, month = reports.month_bounds(request.query_params.get("month", ""))
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        audit.record(
            audit.Action.EXPORT,
            object_type="payroll.report",
            object_repr=f"SIPE {month:02d}/{year}",
            request=request,
        )
        return attachment(
            reports.sipe_workbook(year, month),
            f"cuotas_css_se_{year}{month:02d}.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
