from django.contrib import admin

from .models import Invitation, Role, RoleAssignment


class AllTenantsAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return self.model.all_tenants.select_related("tenant")


@admin.register(Role)
class RoleAdmin(AllTenantsAdmin):
    list_display = ["name", "tenant", "is_system"]
    list_filter = ["is_system"]
    search_fields = ["name", "tenant__name"]


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(AllTenantsAdmin):
    list_display = ["membership", "role", "tenant"]


@admin.register(Invitation)
class InvitationAdmin(AllTenantsAdmin):
    list_display = ["email", "tenant", "status", "expires_at"]
    list_filter = ["status"]
    exclude = ["token_hash"]
