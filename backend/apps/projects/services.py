from typing import Any

from django.db import transaction

from apps.organization.models import CostCenter

from .models import Project


@transaction.atomic
def create_project(**data: Any) -> Project:
    cost_center = CostCenter.objects.create(
        code=data["code"], name=data["name"], kind=CostCenter.Kind.PROJECT
    )
    return Project.objects.create(cost_center=cost_center, **data)


@transaction.atomic
def update_project(project: Project, **data: Any) -> Project:
    for field, value in data.items():
        setattr(project, field, value)
    project.save()
    cc = project.cost_center
    cc.code, cc.name = project.code, project.name
    cc.is_active = project.status != Project.Status.FINISHED
    cc.save(update_fields=["code", "name", "is_active", "updated_at"])
    return project
