import django_filters
from rest_framework import mixins, viewsets

from apps.iam.permissions import TenantPermissionMixin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")

    class Meta:
        model = AuditLog
        fields = ["action", "object_type", "object_id", "actor"]


class AuditLogViewSet(TenantPermissionMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = AuditLogSerializer
    filterset_class = AuditLogFilter
    search_fields = ["object_repr", "actor_email"]
    required_permission = "audit.view"

    def get_queryset(self):
        return AuditLog.objects.all()
