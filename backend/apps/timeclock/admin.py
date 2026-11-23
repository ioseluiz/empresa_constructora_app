from django.contrib import admin

from apps.iam.admin import AllTenantsAdmin

from .models import Device, ImportBatch


@admin.register(Device)
class DeviceAdmin(AllTenantsAdmin):
    list_display = ["name", "brand", "serial_number", "project", "is_active", "tenant"]


@admin.register(ImportBatch)
class ImportBatchAdmin(AllTenantsAdmin):
    list_display = ["original_name", "source", "status", "valid_rows", "tenant", "created_at"]
    list_filter = ["status", "source"]
