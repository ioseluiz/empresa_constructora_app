from datetime import date
from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.hr.models import Employee

from .models import (
    LegalParameter,
    PayrollConcept,
    PayrollLine,
    PayrollLineItem,
    PayrollRun,
    PayrollSettings,
    Payslip,
    RecurringDeduction,
)


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
        fields = [
            "country",
            "occupational_risk_rate",
            "union_dues_rate",
            "deduct_unworked_time",
            "payslip_show_employer",
            "company_bank",
            "company_account_type",
            "company_account_number",
            "ach_routes",
        ]
        read_only_fields = ["country"]

    def validate_occupational_risk_rate(self, value: Any) -> Any:
        if value < 0 or value > 1:
            raise serializers.ValidationError(
                "Indica la tasa como fracción (ej.: 0.0567 = 5.67 %)."
            )
        return value

    def validate_ach_routes(self, value: Any) -> Any:
        from apps.organization.panama import BANKS

        codes = {code for code, _ in BANKS}
        if not isinstance(value, dict) or any(k not in codes for k in value):
            raise serializers.ValidationError("Usa los códigos de banco del catálogo.")
        if any(not str(v).isdigit() for v in value.values() if v):
            raise serializers.ValidationError("Los códigos de ruta son numéricos.")
        return {k: str(v) for k, v in value.items() if v}

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


class PayrollRunSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    scope_display = serializers.CharField(source="get_scope_display", read_only=True)
    run_type_display = serializers.CharField(source="get_run_type_display", read_only=True)
    frequency_display = serializers.CharField(source="get_frequency_display", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    calculated_by_email = serializers.EmailField(
        source="calculated_by.email", read_only=True, default=None
    )
    approved_by_email = serializers.EmailField(
        source="approved_by.email", read_only=True, default=None
    )
    error_count = serializers.IntegerField(read_only=True, default=0)
    warning_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = PayrollRun
        fields = [
            "id",
            "number",
            "run_type",
            "run_type_display",
            "frequency",
            "frequency_display",
            "scope",
            "scope_display",
            "project",
            "project_code",
            "period_start",
            "period_end",
            "pay_date",
            "status",
            "status_display",
            "employee_count",
            "gross",
            "deductions",
            "net",
            "employer_contributions",
            "provisions",
            "notes",
            "parameters",
            "error_count",
            "warning_count",
            "calculated_at",
            "calculated_by_email",
            "approved_at",
            "approved_by_email",
            "paid_at",
            "created_at",
        ]
        read_only_fields = [
            f
            for f in fields
            if f
            not in {
                "run_type",
                "frequency",
                "scope",
                "project",
                "period_start",
                "period_end",
                "pay_date",
            }
        ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        from apps.projects.models import Project

        self.fields["project"].queryset = Project.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        from .runs import decimo_periods

        start, end = attrs["period_start"], attrs["period_end"]
        run_type = attrs.get("run_type", PayrollRun.RunType.REGULAR)
        if end < start:
            raise serializers.ValidationError({"period_end": "Debe ser posterior al inicio."})
        if run_type == PayrollRun.RunType.DECIMO:
            valid = [(s, e) for s, e, _ in decimo_periods(end.year)]
            if (start, end) not in valid:
                raise serializers.ValidationError(
                    {
                        "period_start": "El décimo se paga por cuatrimestre: 16/12-15/04, "
                        "16/04-15/08 o 16/08-15/12."
                    }
                )
            attrs["frequency"] = ""
            return self._common(attrs)
        if run_type == PayrollRun.RunType.REGULAR and not attrs.get("frequency"):
            raise serializers.ValidationError({"frequency": "Indica la frecuencia de pago."})
        if run_type == PayrollRun.RunType.VACATION:
            attrs["frequency"] = ""
        if (end - start).days > 31:
            raise serializers.ValidationError(
                {"period_end": "El período no puede pasar de 31 días."}
            )
        return self._common(attrs)

    def _common(self, attrs: dict) -> dict:
        if attrs["pay_date"] < attrs["period_start"]:
            raise serializers.ValidationError(
                {"pay_date": "No puede ser anterior al inicio del período."}
            )
        if attrs["scope"] == PayrollRun.Scope.PROJECT and not attrs.get("project"):
            raise serializers.ValidationError({"project": "Indica el proyecto de la planilla."})
        return attrs


class PayrollLineItemSerializer(serializers.ModelSerializer):
    cost_center_code = serializers.CharField(
        source="cost_center.code", read_only=True, default=None
    )

    class Meta:
        model = PayrollLineItem
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "quantity",
            "rate",
            "amount",
            "cost_center_code",
            "detail",
        ]
        read_only_fields = fields


class PayrollLineSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_id_number = serializers.CharField(source="employee.id_number", read_only=True)
    warnings = serializers.ListField(child=serializers.CharField(), read_only=True)
    explanation = serializers.ListField(child=serializers.CharField(), read_only=True)
    items = PayrollLineItemSerializer(many=True, read_only=True)

    class Meta:
        model = PayrollLine
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "employee_id_number",
            "pay_basis",
            "gross",
            "deductions",
            "net",
            "employer_contributions",
            "provisions",
            "warnings",
            "explanation",
            "error",
            "items",
        ]
        read_only_fields = fields


class CostCenterTotalSerializer(serializers.Serializer):
    cost_center = serializers.CharField()
    name = serializers.CharField()
    earning = serializers.DecimalField(max_digits=18, decimal_places=2)
    employer = serializers.DecimalField(max_digits=18, decimal_places=2)
    provision = serializers.DecimalField(max_digits=18, decimal_places=2)
    deduction = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_cost = serializers.DecimalField(max_digits=18, decimal_places=2)


class ConceptTotalSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    total = serializers.DecimalField(max_digits=18, decimal_places=2)


class RunTotalsSerializer(serializers.Serializer):
    gross = serializers.DecimalField(max_digits=18, decimal_places=2)
    deductions = serializers.DecimalField(max_digits=18, decimal_places=2)
    net = serializers.DecimalField(max_digits=18, decimal_places=2)
    employer_contributions = serializers.DecimalField(max_digits=18, decimal_places=2)
    provisions = serializers.DecimalField(max_digits=18, decimal_places=2)


class ConsolidatedSerializer(serializers.Serializer):
    runs = serializers.IntegerField()
    employees = serializers.IntegerField()
    totals = RunTotalsSerializer()
    by_cost_center = CostCenterTotalSerializer(many=True)
    by_concept = ConceptTotalSerializer(many=True)


class PayslipSerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    run_number = serializers.IntegerField(source="run.number", read_only=True)
    period_start = serializers.DateField(source="run.period_start", read_only=True)
    period_end = serializers.DateField(source="run.period_end", read_only=True)
    pay_date = serializers.DateField(source="run.pay_date", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id",
            "number",
            "run",
            "run_number",
            "employee",
            "employee_code",
            "employee_name",
            "period_start",
            "period_end",
            "pay_date",
            "net",
            "emailed_at",
            "emailed_to",
            "created_at",
        ]
        read_only_fields = fields


class EmailResultSerializer(serializers.Serializer):
    sent = serializers.IntegerField()
    missing_email = serializers.ListField(child=serializers.CharField())


class AchRowSerializer(serializers.Serializer):
    name = serializers.CharField()
    id_number = serializers.CharField()
    bank = serializers.CharField()
    route = serializers.CharField()
    account_type = serializers.CharField()
    account_number = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class NonAchSerializer(serializers.Serializer):
    employee = serializers.CharField()
    method = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)


class AchSummarySerializer(serializers.Serializer):
    rows = AchRowSerializer(many=True)
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    blocking = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    non_ach = NonAchSerializer(many=True)
