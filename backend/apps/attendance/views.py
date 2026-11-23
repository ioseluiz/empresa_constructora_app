from django.db.models import QuerySet
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, viewsets

from apps.iam.permissions import TenantPermissionMixin, filter_by_project_scope

from .models import TimeEntry
from .serializers import TimeEntrySerializer


class TimeEntryFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte")

    class Meta:
        model = TimeEntry
        fields = ["employee", "project", "cost_center", "hour_type", "day_kind"]


@extend_schema(tags=["marcaciones"])
class TimeEntryViewSet(TenantPermissionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Horas aprobadas (solo lectura): se generan al aprobar jornadas."""

    serializer_class = TimeEntrySerializer
    required_permission = "timeclock.view"
    filterset_class = TimeEntryFilter
    ordering = ["date"]

    def get_queryset(self) -> QuerySet[TimeEntry]:
        qs = TimeEntry.objects.select_related("employee", "project", "cost_center")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return filter_by_project_scope(qs, self.request, "timeclock.view")
