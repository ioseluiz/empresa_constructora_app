from typing import Any

from django.db.models import QuerySet
from django.http import FileResponse
from django_filters import rest_framework as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from apps.audit import services as audit
from apps.iam.permissions import (
    TenantPermissionMixin,
    filter_by_project_scope,
    get_request_permissions,
    get_request_scope,
)
from apps.iam.services import ALL_PROJECTS

from .models import (
    Employee,
    EmployeeDocument,
    EmploymentContract,
    ProjectAssignment,
    SalaryRecord,
)
from .serializers import (
    SALARY_PERMISSION,
    EmployeeDocumentSerializer,
    EmployeeSerializer,
    EmploymentContractSerializer,
    EndContractSerializer,
    ProjectAssignmentSerializer,
    SalaryRecordSerializer,
    current_assignments,
    employees_with_current_data,
)
from .services import create_contract, create_employee, end_contract

VIEW, MANAGE = "hr.employee.view", "hr.employee.manage"


def scope_employees(qs: QuerySet, request: Request, permission: str, prefix: str = "") -> QuerySet:
    """Con un rol limitado a ciertos proyectos solo se ven los empleados asignados (en algún
    momento) a esos proyectos."""
    if get_request_scope(request, permission) == ALL_PROJECTS:
        return qs
    return filter_by_project_scope(
        qs, request, permission, f"{prefix}assignments__project"
    ).distinct()


def ensure_can_manage(request: Request, employee: Employee, project: Any = None) -> None:
    scope = get_request_scope(request, MANAGE)
    if scope == ALL_PROJECTS:
        return
    if project is not None and project.pk not in scope:
        raise PermissionDenied("No tienes permiso sobre ese proyecto.")
    if not employee.assignments.filter(project_id__in=scope).exists():
        raise PermissionDenied("No tienes permiso sobre este empleado.")


def ensure_salary_access(request: Request) -> None:
    if SALARY_PERMISSION not in get_request_permissions(request):
        raise PermissionDenied("Necesitas el permiso para ver salarios.")


class AuditedMixin:
    def audit_update(self, before: dict, obj: Any) -> None:
        changes = audit.diff(before, dict(self.get_serializer(obj).data))  # type: ignore[attr-defined]
        if changes:
            audit.record(audit.Action.UPDATE, obj, request=self.request, changes=changes)  # type: ignore[attr-defined]


class EmployeeFilter(filters.FilterSet):
    project = filters.UUIDFilter(method="filter_project", label="Proyecto actual")

    class Meta:
        model = Employee
        fields = ["status", "payment_method", "is_union_member"]

    def filter_project(self, qs: QuerySet, name: str, value: Any) -> QuerySet:
        ids = current_assignments().filter(project_id=value).values("employee_id")
        return qs.filter(pk__in=ids)


@extend_schema(tags=["personal"])
class EmployeeViewSet(
    TenantPermissionMixin,
    AuditedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Los empleados no se eliminan: se retiran al terminar su contrato."""

    serializer_class = EmployeeSerializer
    permission_resource = "hr.employee"
    filterset_class = EmployeeFilter
    search_fields = [
        "code",
        "first_name",
        "last_name",
        "second_last_name",
        "id_number",
        "css_number",
    ]
    ordering_fields = ["code", "last_name", "hire_date", "created_at"]

    def get_queryset(self) -> QuerySet[Employee]:
        qs = Employee.objects.all()
        if getattr(self, "swagger_fake_view", False):
            return qs
        return employees_with_current_data(scope_employees(qs, self.request, VIEW))

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        if get_request_scope(request, MANAGE) != ALL_PROJECTS:
            raise PermissionDenied("Registrar empleados requiere el permiso sobre toda la empresa.")
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        employee = create_employee(**serializer.validated_data, created_by=self.request.user)
        serializer.instance = employee
        audit.record(audit.Action.CREATE, employee, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        ensure_can_manage(self.request, serializer.instance)  # type: ignore[arg-type]
        before = dict(self.get_serializer(serializer.instance).data)
        employee = serializer.save(updated_by=self.request.user)
        self.audit_update(before, employee)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"], url_path="next-code")
    def next_code(self, request: Request) -> Response:
        from .services import next_employee_code

        return Response({"code": next_employee_code()})


@extend_schema(tags=["personal"])
class ContractViewSet(
    TenantPermissionMixin,
    AuditedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = EmploymentContractSerializer
    permission_resource = "hr.employee"
    action_permissions = {"end": MANAGE}
    filterset_fields = ["employee", "status", "contract_type", "project"]
    pagination_class = None

    def get_queryset(self) -> QuerySet[EmploymentContract]:
        qs = EmploymentContract.objects.select_related(
            "position", "project", "cost_center", "cba_category", "employee"
        ).prefetch_related("salary_history")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "employee__")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        ensure_salary_access(self.request)
        data = dict(serializer.validated_data)
        ensure_can_manage(self.request, data["employee"], data.get("project"))
        contract = create_contract(
            initial_amount=data.pop("initial_amount"),
            uses_cba_rate=data.pop("initial_uses_cba_rate"),
            **data,
            created_by=self.request.user,
        )
        serializer.instance = contract
        audit.record(audit.Action.CREATE, contract, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        contract: EmploymentContract = serializer.instance  # type: ignore[assignment]
        ensure_can_manage(self.request, contract.employee, serializer.validated_data.get("project"))
        if contract.status != EmploymentContract.Status.ACTIVE:
            raise PermissionDenied("Solo se pueden editar contratos vigentes.")
        before = dict(self.get_serializer(contract).data)
        contract = serializer.save(updated_by=self.request.user)
        self.audit_update(before, contract)

    @extend_schema(request=EndContractSerializer, responses=EmploymentContractSerializer)
    @action(detail=True, methods=["post"])
    def end(self, request: Request, pk: str | None = None) -> Response:
        """Termina el contrato (renuncia, despido, fin de obra…). El cálculo de prestaciones
        llega con las liquidaciones."""
        contract = self.get_object()
        ensure_can_manage(request, contract.employee)
        if contract.status != EmploymentContract.Status.ACTIVE:
            raise PermissionDenied("El contrato no está vigente.")
        params = EndContractSerializer(data=request.data, context={"contract": contract})
        params.is_valid(raise_exception=True)
        contract = end_contract(contract, user=request.user, **params.validated_data)
        audit.record(
            audit.Action.UPDATE,
            contract,
            request=request,
            changes={"terminado": {k: str(v) for k, v in params.validated_data.items()}},
        )
        return Response(self.get_serializer(contract).data)


@extend_schema(tags=["personal"])
class SalaryRecordViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Historial salarial. Un aumento se registra con su fecha de vigencia; los registros no se
    editan (corrige con un registro nuevo para que la trazabilidad sea completa)."""

    serializer_class = SalaryRecordSerializer
    action_permissions = {"list": SALARY_PERMISSION, "create": MANAGE}
    filterset_fields = ["contract"]
    pagination_class = None

    def get_queryset(self) -> QuerySet[SalaryRecord]:
        qs = SalaryRecord.objects.select_related("contract")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "contract__employee__")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        ensure_salary_access(self.request)
        ensure_can_manage(self.request, serializer.validated_data["contract"].employee)
        record = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, record, request=self.request, changes=serializer.data)


@extend_schema(tags=["personal"])
class AssignmentViewSet(TenantPermissionMixin, AuditedMixin, viewsets.ModelViewSet):
    serializer_class = ProjectAssignmentSerializer
    permission_resource = "hr.employee"
    filterset_fields = ["employee", "project"]
    pagination_class = None

    def get_queryset(self) -> QuerySet[ProjectAssignment]:
        qs = ProjectAssignment.objects.select_related("project", "position", "employee")
        if getattr(self, "swagger_fake_view", False):
            return qs
        # Un rol por proyecto solo ve las asignaciones de sus proyectos.
        return filter_by_project_scope(qs, self.request, VIEW)

    def _check(self, project: Any) -> None:
        scope = get_request_scope(self.request, MANAGE)
        if scope != ALL_PROJECTS and project.pk not in scope:
            raise PermissionDenied("No tienes permiso sobre ese proyecto.")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        data = serializer.validated_data
        self._check(data["project"])
        obj = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, obj, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        obj: ProjectAssignment = serializer.instance  # type: ignore[assignment]
        self._check(obj.project)
        self._check(serializer.validated_data.get("project", obj.project))
        before = dict(self.get_serializer(obj).data)
        obj = serializer.save(updated_by=self.request.user)
        self.audit_update(before, obj)

    def perform_destroy(self, instance: ProjectAssignment) -> None:
        self._check(instance.project)
        data = dict(self.get_serializer(instance).data)
        audit.record(audit.Action.DELETE, instance, request=self.request, changes=data)
        instance.delete()


@extend_schema_view(
    download=extend_schema(responses={(200, "application/octet-stream"): OpenApiTypes.BINARY})
)
@extend_schema(tags=["personal"])
class DocumentViewSet(TenantPermissionMixin, AuditedMixin, viewsets.ModelViewSet):
    serializer_class = EmployeeDocumentSerializer
    permission_resource = "hr.employee"
    filterset_fields = ["employee", "kind"]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = None
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self) -> QuerySet[EmployeeDocument]:
        qs = EmployeeDocument.objects.select_related("created_by", "employee")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return scope_employees(qs, self.request, VIEW, "employee__")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        ensure_can_manage(self.request, serializer.validated_data["employee"])
        doc = serializer.save(created_by=self.request.user)
        audit.record(audit.Action.CREATE, doc, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        doc: EmployeeDocument = serializer.instance  # type: ignore[assignment]
        ensure_can_manage(self.request, doc.employee)
        if "file" in serializer.validated_data:
            doc.file.delete(save=False)
        before = dict(self.get_serializer(doc).data)
        doc = serializer.save(updated_by=self.request.user)
        self.audit_update(before, doc)

    def perform_destroy(self, instance: EmployeeDocument) -> None:
        ensure_can_manage(self.request, instance.employee)
        data = dict(self.get_serializer(instance).data)
        audit.record(audit.Action.DELETE, instance, request=self.request, changes=data)
        instance.file.delete(save=False)
        instance.delete()

    @action(detail=True, methods=["get"])
    def download(self, request: Request, pk: str | None = None) -> FileResponse:
        """Descarga autenticada (los documentos nunca se sirven como archivos públicos)."""
        doc = self.get_object()
        audit.record(
            audit.Action.EXPORT, doc, request=request, changes={"descarga": doc.original_name}
        )
        response = FileResponse(
            doc.file.open("rb"),
            as_attachment=True,
            filename=doc.original_name,
            content_type=doc.content_type,
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
