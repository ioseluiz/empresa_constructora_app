from datetime import date
from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.hr.models import Employee

from .models import LegalParameter, PayrollConcept, PayrollSettings, RecurringDeduction


class LegalParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalParameter
        fields = [
            "id",
            "country",
            "key",
            "name",
            "value",
            "table",
            "valid_from",
            "legal_basis",
            "notes",
        ]
        read_only_fields = fields


class PayrollSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayrollSettings
        fields = ["country", "occupational_risk_rate", "union_dues_rate", "deduct_unworked_time"]
        read_only_fields = ["country"]

    def validate_occupational_risk_rate(self, value: Any) -> Any:
        if value < 0 or value > 1:
            raise serializers.ValidationError(
                "Indica la tasa como fracción (ej.: 0.0567 = 5.67 %)."
            )
        return value

    def validate_union_dues_rate(self, value: Any) -> Any:
        if value < 0 or value > Decimal("0.2"):
            raise serializers.ValidationError("Indica una fracción entre 0 y 0.2 (20 %).")
        return value


class PayrollConceptSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = PayrollConcept
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "kind_display",
            "taxable_css",
            "taxable_se",
            "taxable_isr",
            "priority",
            "is_legal_order",
            "is_system",
            "accounting_account",
            "is_active",
        ]
        read_only_fields = ["id", "is_system", "kind_display"]

    def validate(self, attrs: dict) -> dict:
        instance: PayrollConcept | None = self.instance
        if instance is not None and instance.is_system:
            locked = {"code", "kind", "taxable_css", "taxable_se", "taxable_isr", "is_legal_order"}
            changed = [f for f in locked if f in attrs and attrs[f] != getattr(instance, f)]
            if changed:
                raise serializers.ValidationError(
                    "En los conceptos del sistema solo se puede cambiar el nombre, la prioridad, "
                    "la cuenta contable y si está activo."
                )
        if instance is None and attrs.get("kind") != PayrollConcept.Kind.DEDUCTION:
            raise serializers.ValidationError(
                {"kind": "Por ahora solo se pueden agregar conceptos de deducción."}
            )
        code = attrs.get("code")
        if code:
            attrs["code"] = code = code.strip().upper()
            qs = PayrollConcept.objects.filter(code=code)
            if instance is not None:
                qs = qs.exclude(pk=instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    {"code": "Ya existe un concepto con este código."}
                )
        return attrs


class RecurringDeductionSerializer(serializers.ModelSerializer):
    concept_name = serializers.CharField(source="concept.name", read_only=True)
    concept_code = serializers.CharField(source="concept.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    balance = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True, allow_null=True
    )

    class Meta:
        model = RecurringDeduction
        fields = [
            "id",
            "employee",
            "employee_name",
            "concept",
            "concept_code",
            "concept_name",
            "amount_per_period",
            "total_amount",
            "paid_amount",
            "balance",
            "start_date",
            "end_date",
            "creditor",
            "reference",
            "is_active",
        ]
        read_only_fields = ["id", "paid_amount", "balance"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]
        self.fields["concept"].queryset = PayrollConcept.objects.filter(  # type: ignore[attr-defined]
            kind=PayrollConcept.Kind.DEDUCTION, is_active=True
        ).exclude(code__in=["CSS", "SE", "ISR", "CUOTA_SINDICAL"])
        if self.instance is not None and not isinstance(self.instance, list):
            self.fields["employee"].read_only = True

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "No puede ser anterior al inicio."})
        concept = attrs.get("concept", getattr(self.instance, "concept", None))
        if (
            concept is not None
            and concept.is_legal_order
            and not attrs.get("reference", getattr(self.instance, "reference", ""))
        ):
            raise serializers.ValidationError(
                {"reference": "Indica el número de oficio o resolución de la orden judicial."}
            )
        return attrs


class PreviewRequestSerializer(serializers.Serializer):
    employee = serializers.PrimaryKeyRelatedField(queryset=Employee.objects.none())
    period_start = serializers.DateField()
    period_end = serializers.DateField()
    pay_date = serializers.DateField(required=False, allow_null=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["employee"].queryset = Employee.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        start: date = attrs["period_start"]
        end: date = attrs["period_end"]
        if end < start:
            raise serializers.ValidationError({"period_end": "Debe ser posterior al inicio."})
        if (end - start).days > 31:
            raise serializers.ValidationError(
                {"period_end": "El período no puede pasar de 31 días."}
            )
        return attrs


class PayLineSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    rate = serializers.DecimalField(max_digits=14, decimal_places=6, allow_null=True)
    cost_center = serializers.CharField(allow_null=True)
    detail = serializers.CharField()


class PreviewResultSerializer(serializers.Serializer):
    lines = PayLineSerializer(many=True)
    gross = serializers.DecimalField(max_digits=18, decimal_places=2)
    deductions = serializers.DecimalField(max_digits=18, decimal_places=2)
    net = serializers.DecimalField(max_digits=18, decimal_places=2)
    employer_cost = serializers.DecimalField(max_digits=18, decimal_places=2)
    warnings = serializers.ListField(child=serializers.CharField())
    explanation = serializers.ListField(child=serializers.CharField())
    parameters = serializers.DictField(child=serializers.CharField())
