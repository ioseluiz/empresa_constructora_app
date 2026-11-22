from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from apps.audit import services as audit
from apps.iam.permissions import (
    TenantPermissionMixin,
    filter_by_project_scope,
    get_request_scope,
)
from apps.iam.services import ALL_PROJECTS

from .models import Project
from .serializers import ProjectSerializer
from .services import create_project, update_project


@extend_schema(tags=["proyectos"])
class ProjectViewSet(
    TenantPermissionMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Los proyectos no se eliminan (tienen historial de planilla): se marcan como terminados."""

    serializer_class = ProjectSerializer
    permission_resource = "projects"
    filterset_fields = ["status", "province"]
    search_fields = ["code", "name", "client"]
    ordering_fields = ["code", "name", "start_date", "created_at"]

    def get_queryset(self) -> QuerySet[Project]:
        qs = Project.objects.select_related("cost_center")
        if getattr(self, "swagger_fake_view", False):
            return qs
        return filter_by_project_scope(qs, self.request, "projects.view", "pk")

    def perform_create(self, serializer: serializers.BaseSerializer) -> None:
        if get_request_scope(self.request, "projects.manage") != ALL_PROJECTS:
            raise PermissionDenied("Crear proyectos requiere el permiso sobre toda la empresa.")
        project = create_project(**serializer.validated_data, created_by=self.request.user)
        serializer.instance = project
        audit.record(audit.Action.CREATE, project, request=self.request, changes=serializer.data)

    def perform_update(self, serializer: serializers.BaseSerializer) -> None:
        project: Project = serializer.instance  # type: ignore[assignment]
        scope = get_request_scope(self.request, "projects.manage")
        if scope != ALL_PROJECTS and project.pk not in scope:
            raise PermissionDenied("No puedes editar este proyecto.")
        before = dict(ProjectSerializer(project).data)
        project = update_project(project, **serializer.validated_data, updated_by=self.request.user)
        changes = audit.diff(before, dict(ProjectSerializer(project).data))
        if changes:
            audit.record(audit.Action.UPDATE, project, request=self.request, changes=changes)
