from django.contrib import admin

from apps.iam.admin import AllTenantsAdmin

from .models import TimeEntry


@admin.register(TimeEntry)
class TimeEntryAdmin(AllTenantsAdmin):
    list_display = ["employee", "date", "hour_type", "hours", "project", "locked", "tenant"]
    list_filter = ["hour_type", "day_kind", "locked"]
