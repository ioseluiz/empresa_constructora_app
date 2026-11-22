import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from django.db.models import Prefetch, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.iam.permissions import get_request_permissions
from apps.organization.models import CBACategory, CostCenter, Position
from apps.organization.panama import CEDULA_REGEX
from apps.projects.models import Project

from .models import (
    Employee,
    EmployeeDocument,
    EmploymentContract,
    ProjectAssignment,
    SalaryRecord,
)
from .services import overlapping

SALARY_PERMISSION = "hr.salary.view"
MAX_DOCUMENT_SIZE = 10 * 1024 * 1024
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
}


def can_view_salary(context: Mapping[str, Any]) -> bool:
    request = context.get("request")
    if request is None or not hasattr(request, "membership"):
        return True  # generación del esquema OpenAPI
    return SALARY_PERMISSION in get_request_permissions(request)


class RefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class EmployeeSerializer(serializers.ModelSerializer):
    """Los datos bancarios solo se muestran y editan con `hr.salary.view`."""

    BANK_FIELDS = ("bank", "bank_display", "account_type", "account_number")

    full_name = serializers.CharField(read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    bank_display = serializers.CharField(source="get_bank_display", read_only=True)
    payment_method_display = serializers.CharField(
        source="get_payment_method_display", read_only=True
    )
    current_projects = serializers.SerializerMethodField()
    current_position = serializers.SerializerMethodField()
    code = serializers.CharField(max_length=20, required=False, allow_blank=True)

    class Meta:
        model = Employee
        fields = [
            "id",
            "code",
            "first_name",
            "middle_name",
            "last_name",
            "second_last_name",
            "full_name",
            "id_type",
            "id_number",
            "css_number",
            "birth_date",
            "sex",
            "marital_status",
            "nationality",
            "email",
            "phone",
            "address",
            "province",
            "emergency_contact_name",
            "emergency_contact_phone",
            "payment_method",
            "payment_method_display",
            "bank",
            "bank_display",
            "account_type",
            "account_number",
            "hire_date",
            "termination_date",
            "status",
            "status_display",
            "is_union_member",
            "notes",
            "current_projects",
            "current_position",
            "created_at",
        ]
        read_only_fields = ["id", "termination_date", "status", "created_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not can_view_salary(self.context):
            for name in self.BANK_FIELDS:
                self.fields.pop(name, None)

    @extend_schema_field(RefSerializer(many=True))
    def get_current_projects(self, obj: Employee) -> list[dict]:
        rows = getattr(obj, "current_assignments", None)
        if rows is None:
            rows = list(current_assignments().filter(employee=obj).select_related("project"))
        return [{"id": a.project.pk, "code": a.project.code, "name": a.project.name} for a in rows]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_current_position(self, obj: Employee) -> str | None:
        contracts = getattr(obj, "active_contracts", None)
        if contracts is None:
            contracts = list(obj.contracts.filter(status=EmploymentContract.Status.ACTIVE))
        return contracts[0].position.name if contracts else None

    def validate_code(self, value: str) -> str:
        value = value.strip().upper()
        if not value:
            return value
        qs = Employee.objects.filter(code__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya existe un empleado con este número.")
        return value

    def validate_id_number(self, value: str) -> str:
        return value.strip().upper()

    def validate(self, attrs: dict) -> dict:
        def current(field: str) -> Any:
            return attrs.get(field, getattr(self.instance, field, ""))

        id_type, id_number = current("id_type") or Employee.IdType.CEDULA, current("id_number")
        if id_type == Employee.IdType.CEDULA and not re.match(CEDULA_REGEX, id_number or ""):
            raise serializers.ValidationError(
                {"id_number": "Formato de cédula inválido. Ej.: 8-123-4567, 4PI-12-345, E-8-1234."}
            )
        duplicates = Employee.objects.filter(id_type=id_type, id_number=id_number)
        if self.instance is not None:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError(
                {"id_number": "Ya existe un empleado con esta identificación."}
            )
        if current("payment_method") == Employee.PaymentMethod.ACH:
            missing = {
                f: "Requerido para pago por ACH."
                for f in ("bank", "account_type", "account_number")
                if not current(f)
            }
            if missing and "bank" not in self.fields:
                raise serializers.ValidationError(
                    {"payment_method": "Solo quien ve salarios puede configurar el pago ACH."}
                )
            if missing:
                raise serializers.ValidationError(missing)
        birth, hire = current("birth_date"), current("hire_date")
        if birth and hire and (hire.year - birth.year) < 14:
            raise serializers.ValidationError(
                {"birth_date": "El empleado debe tener al menos 14 años a la fecha de ingreso."}
            )
        return attrs


class SalaryRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryRecord
        fields = ["id", "contract", "valid_from", "amount", "uses_cba_rate", "reason", "created_at"]
        read_only_fields = ["id", "created_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["contract"].queryset = EmploymentContract.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        contract: EmploymentContract = attrs.get("contract") or self.instance.contract  # type: ignore[union-attr]
        valid_from: date = attrs.get("valid_from") or self.instance.valid_from  # type: ignore[union-attr]
        uses_cba = attrs.get("uses_cba_rate", getattr(self.instance, "uses_cba_rate", False))
        amount = attrs.get("amount", getattr(self.instance, "amount", None))
        if contract.status == EmploymentContract.Status.CANCELLED:
            raise serializers.ValidationError("El contrato está anulado.")
        if valid_from < contract.start_date or (
            contract.end_date and valid_from > contract.end_date
        ):
            raise serializers.ValidationError(
                {"valid_from": "La fecha debe estar dentro del período del contrato."}
            )
        validate_salary(contract.pay_basis, contract.cba_category, uses_cba, amount)
        if uses_cba:
            attrs["amount"] = None
        dupes = SalaryRecord.objects.filter(contract=contract, valid_from=valid_from)
        if self.instance is not None:
            dupes = dupes.exclude(pk=self.instance.pk)
        if dupes.exists():
            raise serializers.ValidationError(
                {"valid_from": "Ya hay un salario registrado con esta fecha."}
            )
        return attrs


def validate_salary(
    pay_basis: str, cba_category: CBACategory | None, uses_cba: bool, amount: Any
) -> None:
    if uses_cba:
        if pay_basis != EmploymentContract.PayBasis.HOURLY or cba_category is None:
            raise serializers.ValidationError(
                {"uses_cba_rate": "Solo para contratos por hora con categoría de convención."}
            )
        return
    if amount is None or amount <= 0:
        raise serializers.ValidationError({"amount": "Indica un monto mayor que cero."})


class EmploymentContractSerializer(serializers.ModelSerializer):
    contract_type_display = serializers.CharField(
        source="get_contract_type_display", read_only=True
    )
    pay_frequency_display = serializers.CharField(
        source="get_pay_frequency_display", read_only=True
    )
    pay_basis_display = serializers.CharField(source="get_pay_basis_display", read_only=True)
    shift_display = serializers.CharField(source="get_shift_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    position_name = serializers.CharField(source="position.name", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)
    cba_category_name = serializers.CharField(
        source="cba_category.name", read_only=True, default=None
    )
    current_salary = serializers.SerializerMethodField()
    initial_amount = serializers.DecimalField(
        max_digits=12, decimal_places=4, write_only=True, required=False, allow_null=True
    )
    initial_uses_cba_rate = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = EmploymentContract
        fields = [
            "id",
            "employee",
            "contract_type",
            "contract_type_display",
            "start_date",
            "end_date",
            "position",
            "position_name",
            "project",
            "project_code",
            "cost_center",
            "cost_center_code",
            "pay_frequency",
            "pay_frequency_display",
            "pay_basis",
            "pay_basis_display",
            "shift",
            "shift_display",
            "weekly_hours",
            "applies_cba",
            "cba_category",
            "cba_category_name",
            "status",
            "status_display",
            "end_reason",
            "notes",
            "current_salary",
            "initial_amount",
            "initial_uses_cba_rate",
            "created_at",
        ]
        read_only_fields = ["id", "status", "end_reason", "created_at"]
        extra_kwargs = {"cost_center": {"required": False}}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        querysets = {
            "employee": Employee.objects.all(),
            "position": Position.objects.all(),
            "project": Project.objects.all(),
            "cost_center": CostCenter.objects.all(),
            "cba_category": CBACategory.objects.all(),
        }
        for name, qs in querysets.items():
            self.fields[name].queryset = qs  # type: ignore[attr-defined]
        if self.instance is not None and not isinstance(self.instance, list):
            self.fields["employee"].read_only = True

    @extend_schema_field(SalaryRecordSerializer(allow_null=True))
    def get_current_salary(self, obj: EmploymentContract) -> dict | None:
        if not can_view_salary(self.context):
            return None
        history = sorted(obj.salary_history.all(), key=lambda r: r.valid_from, reverse=True)
        return SalaryRecordSerializer(history[0]).data if history else None

    def validate(self, attrs: dict) -> dict:
        def current(field: str) -> Any:
            return attrs.get(field, getattr(self.instance, field, None))

        employee: Employee = current("employee")
        start, end = current("start_date"), current("end_date")
        ctype, project = current("contract_type"), current("project")
        errors: dict[str, str] = {}
        if end and end < start:
            errors["end_date"] = "El fin no puede ser anterior al inicio."
        if ctype == EmploymentContract.Type.FIXED_TERM and not end:
            errors["end_date"] = "Los contratos por tiempo definido requieren fecha de fin."
        if ctype == EmploymentContract.Type.PROJECT and not project:
            errors["project"] = "Indica la obra del contrato por obra determinada."
        if start and employee and start < employee.hire_date:
            errors["start_date"] = "No puede ser anterior a la fecha de ingreso del empleado."
        position: Position | None = current("position")
        if current("applies_cba"):
            category = current("cba_category") or (position.cba_category if position else None)
            if category is None:
                errors["cba_category"] = "Indica la categoría de la convención."
            attrs["cba_category"] = category
        elif "applies_cba" in attrs:
            attrs["cba_category"] = None
        if errors:
            raise serializers.ValidationError(errors)

        others = EmploymentContract.objects.filter(employee=employee).exclude(
            status=EmploymentContract.Status.CANCELLED
        )
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if overlapping(others, start, end).exists():
            raise serializers.ValidationError(
                {"start_date": "El empleado ya tiene un contrato vigente en esas fechas."}
            )

        if self.instance is None:
            uses_cba = attrs.pop("initial_uses_cba_rate", False)
            amount = attrs.pop("initial_amount", None)
            validate_salary(current("pay_basis"), attrs.get("cba_category"), uses_cba, amount)
            attrs["initial_uses_cba_rate"], attrs["initial_amount"] = uses_cba, amount
        else:
            attrs.pop("initial_uses_cba_rate", None)
            attrs.pop("initial_amount", None)
        return attrs


class EndContractSerializer(serializers.Serializer):
    end_date = serializers.DateField()
    reason = serializers.CharField(max_length=255)

    def validate_end_date(self, value: Any) -> Any:
        contract: EmploymentContract = self.context["contract"]
        if value < contract.start_date:
            raise serializers.ValidationError("No puede ser anterior al inicio del contrato.")
        return value


class ProjectAssignmentSerializer(serializers.ModelSerializer):
    project_ref = RefSerializer(source="project", read_only=True)
    position_name = serializers.CharField(source="position.name", read_only=True, default=None)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_code = serializers.CharField(source="employee.code", read_only=True)

    class Meta:
        model = ProjectAssignment
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "project",
            "project_ref",
            "position",
            "position_name",
            "start_date",
            "end_date",
            "notes",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]
        self.fields["project"].queryset = Project.objects.all()  # type: ignore[attr-defined]
        self.fields["position"].queryset = Position.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        def current(field: str) -> Any:
            return attrs.get(field, getattr(self.instance, field, None))

        employee, project = current("employee"), current("project")
        start, end = current("start_date"), current("end_date")
        if end and end < start:
            raise serializers.ValidationError({"end_date": "No puede ser anterior al inicio."})
        if start < employee.hire_date:
            raise serializers.ValidationError(
                {"start_date": "No puede ser anterior a la fecha de ingreso del empleado."}
            )
        if project.status == Project.Status.FINISHED and self.instance is None:
            raise serializers.ValidationError({"project": "El proyecto está terminado."})
        others = ProjectAssignment.objects.filter(employee=employee, project=project)
        if self.instance is not None:
            others = others.exclude(pk=self.instance.pk)
        if overlapping(others, start, end).exists():
            raise serializers.ValidationError(
                {"start_date": "El empleado ya está asignado a este proyecto en esas fechas."}
            )
        return attrs


class EmployeeDocumentSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    file = serializers.FileField(write_only=True)
    uploaded_by = serializers.EmailField(source="created_by.email", read_only=True, default=None)

    class Meta:
        model = EmployeeDocument
        fields = [
            "id",
            "employee",
            "kind",
            "kind_display",
            "title",
            "file",
            "original_name",
            "content_type",
            "size",
            "expires_on",
            "uploaded_by",
            "created_at",
        ]
        read_only_fields = ["id", "original_name", "content_type", "size", "created_at"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]
        if self.instance is not None:
            self.fields["employee"].read_only = True
            self.fields["file"].required = False

    def validate_file(self, value: Any) -> Any:
        if value.size > MAX_DOCUMENT_SIZE:
            raise serializers.ValidationError("El archivo supera el máximo de 10 MB.")
        content_type = getattr(value, "content_type", "")
        if content_type not in ALLOWED_DOCUMENT_TYPES:
            raise serializers.ValidationError("Solo se aceptan archivos PDF, JPG o PNG.")
        head = value.read(8)
        value.seek(0)
        signatures = {
            "application/pdf": (b"%PDF",),
            "image/jpeg": (b"\xff\xd8\xff",),
            "image/png": (b"\x89PNG",),
        }
        if not head.startswith(signatures[content_type]):
            raise serializers.ValidationError("El contenido no corresponde al tipo de archivo.")
        return value

    def validate(self, attrs: dict) -> dict:
        upload = attrs.get("file")
        if upload is not None:
            attrs["original_name"] = upload.name[:255]
            attrs["content_type"] = upload.content_type
            attrs["size"] = upload.size
        return attrs


def current_assignments() -> Any:
    today = timezone.localdate()
    return ProjectAssignment.objects.filter(
        Q(end_date__isnull=True) | Q(end_date__gte=today), start_date__lte=today
    )


def employees_with_current_data(qs: Any) -> Any:
    """Prefetch para listar empleados con proyectos y puesto actuales sin N+1."""
    return qs.prefetch_related(
        Prefetch(
            "assignments",
            queryset=current_assignments().select_related("project"),
            to_attr="current_assignments",
        ),
        Prefetch(
            "contracts",
            queryset=EmploymentContract.objects.filter(
                status=EmploymentContract.Status.ACTIVE
            ).select_related("position"),
            to_attr="active_contracts",
        ),
    )
