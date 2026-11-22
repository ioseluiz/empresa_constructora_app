from django.contrib import admin

from apps.iam.admin import AllTenantsAdmin

from .models import Project


@admin.register(Project)
class ProjectAdmin(AllTenantsAdmin):
    list_display = ["code", "name", "status", "tenant", "start_date"]
    list_filter = ["status"]
    search_fields = ["code", "name"]
