from rest_framework import serializers

from .models import TimeEntry


class TimeEntrySerializer(serializers.ModelSerializer):
    employee_code = serializers.CharField(source="employee.code", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True, default=None)
    cost_center_code = serializers.CharField(source="cost_center.code", read_only=True)
    hour_type_display = serializers.CharField(source="get_hour_type_display", read_only=True)

    class Meta:
        model = TimeEntry
        fields = [
            "id",
            "employee",
            "employee_code",
            "employee_name",
            "date",
            "project",
            "project_code",
            "cost_center",
            "cost_center_code",
            "hour_type",
            "hour_type_display",
            "day_kind",
            "jornada",
            "hours",
            "workday",
            "locked",
        ]
        read_only_fields = fields
