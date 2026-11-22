from rest_framework import serializers

from .models import Project


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    province_display = serializers.CharField(source="get_province_display", read_only=True)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "code",
            "name",
            "client",
            "province",
            "province_display",
            "address",
            "status",
            "status_display",
            "start_date",
            "estimated_end_date",
            "actual_end_date",
            "contract_amount",
            "description",
            "cost_center",
            "cost_center_code",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status_display",
            "province_display",
            "cost_center",
            "cost_center_code",
            "created_at",
        ]

    def validate_code(self, value: str) -> str:
        from apps.organization.models import CostCenter

        value = value.upper()
        projects = Project.objects.filter(code__iexact=value)
        centers = CostCenter.objects.filter(code__iexact=value)
        if self.instance is not None:
            projects = projects.exclude(pk=self.instance.pk)
            centers = centers.exclude(pk=self.instance.cost_center_id)
        if projects.exists() or centers.exists():
            raise serializers.ValidationError(
                "Ya existe un proyecto o centro de costo con este código."
            )
        return value

    def validate(self, attrs: dict) -> dict:
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("estimated_end_date", getattr(self.instance, "estimated_end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"estimated_end_date": "El fin estimado no puede ser anterior al inicio."}
            )
        return attrs
