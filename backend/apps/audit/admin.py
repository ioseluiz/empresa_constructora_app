from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "tenant", "actor_email", "action", "object_type", "object_repr"]
    list_filter = ["action", "object_type"]
    search_fields = ["actor_email", "object_repr", "object_id"]

    def get_queryset(self, request):
        return AuditLog.all_tenants.select_related("tenant")

    def has_add_permission(self, request, obj=None) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
