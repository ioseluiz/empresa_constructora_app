from datetime import date, datetime, time
from pathlib import PurePath
from typing import Any
from zoneinfo import ZoneInfo

from rest_framework import serializers

from apps.core.tenancy import require_current_tenant
from apps.hr.models import Employee
from apps.projects.models import Project

from .models import ClockCode, Device, ImportBatch, ImportRow, ImportTemplate, Punch
from .services import normalize_code

MAX_FILE_SIZE = 10 * 1024 * 1024
EXTENSIONS = {
    ImportBatch.Source.ZKTECO: {".dat", ".txt", ".csv", ".log"},
    ImportBatch.Source.TEMPLATE: {".csv", ".txt", ".xlsx", ".xlsm"},
}


def local_datetime(day: date, at: time) -> datetime:
    return datetime.combine(
        day, at.replace(microsecond=0), ZoneInfo(require_current_tenant().timezone)
    )


class DeviceSerializer(serializers.ModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    brand_display = serializers.CharField(source="get_brand_display", read_only=True)

    class Meta:
        model = Device
        fields = [
            "id",
            "name",
            "brand",
            "brand_display",
            "model",
            "serial_number",
            "project",
            "project_code",
            "location",
            "is_active",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.all()  # type: ignore[attr-defined]

    def validate_serial_number(self, value: str) -> str:
        value = value.strip().upper()
        qs = Device.objects.filter(serial_number__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if value and qs.exists():
            raise serializers.ValidationError("Ya existe un reloj con este número de serie.")
        return value


class ClockCodeSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)

    class Meta:
        model = ClockCode
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "device",
            "device_name",
            "code",
        ]
        read_only_fields = ["id"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]
        self.fields["device"].queryset = Device.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        def current(f: str) -> Any:
            return attrs.get(f, getattr(self.instance, f, None))

        code, device = current("code").strip().upper(), current("device")
        attrs["code"] = code
        clashes = [
            c
            for c in ClockCode.objects.filter(device=device).select_related("employee")
            if normalize_code(c.code) == normalize_code(code)
            and (self.instance is None or c.pk != self.instance.pk)
        ]
        if clashes:
            where = f"en {device.name}" if device else "para todos los relojes"
            raise serializers.ValidationError(
                {"code": f"El código ya está asignado {where} a {clashes[0].employee.full_name}."}
            )
        return attrs


class ImportTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportTemplate
        fields = [
            "id",
            "name",
            "has_header",
            "delimiter",
            "employee_key",
            "employee_column",
            "datetime_column",
            "date_column",
            "time_column",
            "date_format",
            "time_format",
            "direction_column",
            "in_values",
            "out_values",
            "device_column",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs: dict) -> dict:
        def current(f: str) -> Any:
            return attrs.get(f, getattr(self.instance, f, ""))

        if not current("datetime_column") and not (
            current("date_column") and current("time_column")
        ):
            raise serializers.ValidationError(
                {
                    "datetime_column": (
                        "Indica la columna de fecha y hora, o las columnas de fecha y de hora."
                    )
                }
            )
        for field in ("date_format", "time_format"):
            if "%" not in current(field):
                raise serializers.ValidationError({field: "Usa códigos como %d/%m/%Y o %H:%M."})
        return attrs


class ImportBatchSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    template_name = serializers.CharField(source="template.name", read_only=True, default=None)
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    file = serializers.FileField(write_only=True)
    punch_count = serializers.SerializerMethodField()

    class Meta:
        model = ImportBatch
        fields = [
            "id",
            "source",
            "source_display",
            "template",
            "template_name",
            "device",
            "device_name",
            "project",
            "project_code",
            "file",
            "original_name",
            "status",
            "status_display",
            "error",
            "total_rows",
            "valid_rows",
            "error_rows",
            "duplicate_rows",
            "first_punch",
            "last_punch",
            "punch_count",
            "confirmed_at",
            "reverted_at",
            "revert_reason",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = [
            f for f in fields if f not in {"source", "template", "device", "project", "file"}
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = ImportTemplate.objects.all()  # type: ignore[attr-defined]
        self.fields["device"].queryset = Device.objects.all()  # type: ignore[attr-defined]
        self.fields["project"].queryset = Project.objects.all()  # type: ignore[attr-defined]

    def get_punch_count(self, obj: ImportBatch) -> int:
        return getattr(obj, "active_punches", None) or 0

    def validate(self, attrs: dict) -> dict:
        source, upload = attrs["source"], attrs["file"]
        if source == ImportBatch.Source.ZKTECO and not attrs.get("device"):
            raise serializers.ValidationError({"device": "Indica de qué reloj es el archivo."})
        if source == ImportBatch.Source.TEMPLATE and not attrs.get("template"):
            raise serializers.ValidationError({"template": "Selecciona la plantilla de columnas."})
        if upload.size > MAX_FILE_SIZE:
            raise serializers.ValidationError({"file": "El archivo supera el máximo de 10 MB."})
        ext = PurePath(upload.name).suffix.lower()
        if ext not in EXTENSIONS[source]:
            allowed = ", ".join(sorted(EXTENSIONS[source]))
            raise serializers.ValidationError({"file": f"Extensión no admitida. Usa: {allowed}."})
        attrs["original_name"] = upload.name[:255]
        return attrs


class ImportRowSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True, default=None)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True, default=None)
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)

    class Meta:
        model = ImportRow
        fields = [
            "id",
            "row_number",
            "raw",
            "raw_code",
            "employee",
            "employee_code",
            "employee_name",
            "timestamp",
            "direction",
            "device_name",
            "status",
            "message",
        ]
        read_only_fields = fields


class RevertSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class PunchSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True, default=None)
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )
    voided_by_email = serializers.EmailField(source="voided_by.email", read_only=True, default=None)

    class Meta:
        model = Punch
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "timestamp",
            "direction",
            "direction_display",
            "source",
            "source_display",
            "device",
            "device_name",
            "project",
            "project_code",
            "batch",
            "corrects",
            "reason",
            "is_void",
            "voided_at",
            "voided_by_email",
            "void_reason",
            "created_by_email",
            "created_at",
        ]
        read_only_fields = fields


class ManualPunchSerializer(serializers.Serializer):
    employees = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.none(), many=True)
    date = serializers.DateField()
    time = serializers.TimeField()
    direction = serializers.ChoiceField(choices=Punch.Direction.choices)
    project = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.none(), allow_null=True, required=False
    )
    reason = serializers.CharField(max_length=200)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employees"].child_relation.queryset = Employee.objects.all()  # type: ignore[attr-defined]
        self.fields["project"].queryset = Project.objects.all()  # type: ignore[attr-defined]

    def validate_employees(self, value: list[Employee]) -> list[Employee]:
        if not value:
            raise serializers.ValidationError("Selecciona al menos un empleado.")
        if len(value) > 500:
            raise serializers.ValidationError("Máximo 500 empleados por registro.")
        return value

    def validate(self, attrs: dict) -> dict:
        attrs["timestamp"] = local_datetime(attrs.pop("date"), attrs.pop("time"))
        validate_timestamp_for(attrs["employees"], attrs["timestamp"])
        return attrs


def validate_timestamp_for(employees: list[Employee], timestamp: datetime) -> None:
    from django.utils import timezone

    if timestamp > timezone.now():
        raise serializers.ValidationError({"time": "No se pueden registrar marcaciones futuras."})
    day = timestamp.date()
    outside = [
        e.full_name
        for e in employees
        if day < e.hire_date or (e.termination_date and day > e.termination_date)
    ]
    if outside:
        raise serializers.ValidationError(
            {"employees": f"Sin relación laboral en esa fecha: {', '.join(outside[:5])}."}
        )


class CorrectPunchSerializer(serializers.Serializer):
    date = serializers.DateField()
    time = serializers.TimeField()
    direction = serializers.ChoiceField(choices=Punch.Direction.choices)
    reason = serializers.CharField(max_length=200)

    def validate(self, attrs: dict) -> dict:
        punch: Punch = self.context["punch"]
        attrs["timestamp"] = local_datetime(attrs.pop("date"), attrs.pop("time"))
        validate_timestamp_for([punch.employee], attrs["timestamp"])
        taken = Punch.objects.filter(
            employee=punch.employee, timestamp=attrs["timestamp"], is_void=False
        ).exclude(pk=punch.pk)
        if taken.exists():
            raise serializers.ValidationError({"time": "Ya existe una marcación a esa hora."})
        return attrs


class VoidPunchSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200)


class ManualPunchResultSerializer(serializers.Serializer):
    created = PunchSerializer(many=True)
    skipped = serializers.ListField(child=serializers.CharField())


class ImportRowPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ImportRowSerializer(many=True)
