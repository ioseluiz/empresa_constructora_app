from datetime import date, timedelta
from typing import Any

from rest_framework import serializers

from apps.hr.models import Employee

from .models import VacationAdjustment, VacationRequest
from .services import overlapping_requests


class VacationRequestSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_mode_display = serializers.CharField(source="get_payment_mode_display", read_only=True)
    decided_by_email = serializers.EmailField(
        source="decided_by.email", read_only=True, default=None
    )
    is_paid = serializers.BooleanField(read_only=True)
    paid_run_number = serializers.IntegerField(
        source="paid_line.run.number", read_only=True, default=None
    )

    class Meta:
        model = VacationRequest
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "start_date",
            "end_date",
            "days",
            "payment_mode",
            "payment_mode_display",
            "status",
            "status_display",
            "notes",
            "decided_at",
            "decided_by_email",
            "reject_reason",
            "is_paid",
            "paid_amount",
            "paid_run_number",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "end_date",
            "status",
            "decided_at",
            "reject_reason",
            "paid_amount",
            "created_at",
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.filter(status="active")  # type: ignore[attr-defined]
        if self.instance is not None and not isinstance(self.instance, list):
            self.fields["employee"].read_only = True

    def validate(self, attrs: dict) -> dict:
        employee: Employee = attrs.get("employee") or self.instance.employee  # type: ignore[union-attr]
        start: date = attrs.get("start_date") or self.instance.start_date  # type: ignore[union-attr]
        days: int | None = attrs.get("days", getattr(self.instance, "days", None))
        if days is None or days < 1 or days > 90:
            raise serializers.ValidationError({"days": "Indica entre 1 y 90 días."})
        end = start + timedelta(days=days - 1)
        if start < employee.hire_date:
            raise serializers.ValidationError({"start_date": "Es anterior a la fecha de ingreso."})
        if overlapping_requests(employee, start, end, exclude=getattr(self.instance, "pk", None)):
            raise serializers.ValidationError(
                {"start_date": "Se cruza con otras vacaciones solicitadas o aprobadas."}
            )
        attrs["end_date"] = end
        return attrs


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class VacationAdjustmentSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    created_by_email = serializers.EmailField(
        source="created_by.email", read_only=True, default=None
    )

    class Meta:
        model = VacationAdjustment
        fields = ["id", "employee", "employee_name", "date", "days", "reason", "created_by_email"]
        read_only_fields = ["id"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]


class BalanceSerializer(serializers.Serializer):
    employee = serializers.UUIDField()
    employee_code = serializers.CharField()
    employee_name = serializers.CharField()
    hire_date = serializers.DateField()
    earned = serializers.DecimalField(max_digits=8, decimal_places=2)
    taken = serializers.IntegerField()
    scheduled = serializers.IntegerField()
    adjustments = serializers.DecimalField(max_digits=8, decimal_places=2)
    available = serializers.DecimalField(max_digits=8, decimal_places=2)
    pending_requests = serializers.IntegerField()
