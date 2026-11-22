from datetime import date

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import CBACategory, CBAWageRate, CostCenter, Holiday, Position


class UniqueCodeMixin:
    """Valida código único por empresa con un mensaje claro (la BD también lo exige)."""

    def validate_code(self, value: str) -> str:
        model = self.Meta.model  # type: ignore[attr-defined]
        qs = model.objects.filter(code__iexact=value)
        if self.instance is not None:  # type: ignore[attr-defined]
            qs = qs.exclude(pk=self.instance.pk)  # type: ignore[attr-defined]
        if qs.exists():
            raise serializers.ValidationError("Ya existe un registro con este código.")
        return value.upper()


class CostCenterSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    project_id = serializers.SerializerMethodField()

    class Meta:
        model = CostCenter
        fields = ["id", "code", "name", "kind", "kind_display", "parent", "is_active", "project_id"]
        read_only_fields = ["id", "kind_display", "project_id"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = CostCenter.objects.all()  # type: ignore[attr-defined]

    def get_project_id(self, obj: CostCenter) -> str | None:
        project = getattr(obj, "project", None)
        return str(project.pk) if project else None

    def validate_kind(self, value: str) -> str:
        if value == CostCenter.Kind.PROJECT:
            raise serializers.ValidationError(
                "Los centros de costo de proyecto se crean desde Proyectos."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        instance = self.instance
        if instance is not None and instance.kind == CostCenter.Kind.PROJECT:
            raise serializers.ValidationError(
                "Este centro de costo pertenece a un proyecto; edítalo desde Proyectos."
            )
        parent = attrs.get("parent")
        node = parent
        while node is not None and instance is not None:
            if node.pk == instance.pk:
                raise serializers.ValidationError({"parent": "Se formaría un ciclo."})
            node = node.parent
        return attrs


class CBAWageRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CBAWageRate
        fields = ["id", "category", "hourly_rate", "valid_from", "source"]
        read_only_fields = ["id"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = CBACategory.objects.all()  # type: ignore[attr-defined]

    def validate(self, attrs: dict) -> dict:
        category = attrs.get("category") or getattr(self.instance, "category", None)
        valid_from = attrs.get("valid_from") or getattr(self.instance, "valid_from", None)
        qs = CBAWageRate.objects.filter(category=category, valid_from=valid_from)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                {"valid_from": "Ya hay una tarifa vigente desde esa fecha para esta categoría."}
            )
        return attrs


class CBACategorySerializer(UniqueCodeMixin, serializers.ModelSerializer):
    current_rate = serializers.SerializerMethodField()

    class Meta:
        model = CBACategory
        fields = ["id", "code", "name", "description", "is_active", "current_rate"]
        read_only_fields = ["id", "current_rate"]

    @extend_schema_field(CBAWageRateSerializer(allow_null=True))
    def get_current_rate(self, obj: CBACategory) -> dict | None:
        rate = obj.rate_on(date.today())
        return CBAWageRateSerializer(rate).data if rate else None


class PositionSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    area_display = serializers.CharField(source="get_area_display", read_only=True)
    cba_category_name = serializers.CharField(
        source="cba_category.name", read_only=True, default=None
    )

    class Meta:
        model = Position
        fields = [
            "id",
            "code",
            "name",
            "area",
            "area_display",
            "cba_category",
            "cba_category_name",
            "description",
            "is_active",
        ]
        read_only_fields = ["id", "area_display", "cba_category_name"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["cba_category"].queryset = CBACategory.objects.all()  # type: ignore[attr-defined]


class HolidaySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = Holiday
        fields = ["id", "date", "name", "kind", "kind_display", "is_paid_rest"]
        read_only_fields = ["id", "kind_display"]

    def validate_date(self, value: date) -> date:
        qs = Holiday.objects.filter(date=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ya hay un feriado registrado en esa fecha.")
        return value


class GenerateHolidaysSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100)
