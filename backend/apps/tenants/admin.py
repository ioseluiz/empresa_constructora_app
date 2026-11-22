from django.contrib import admin

from .models import Membership, Tenant


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ["user"]
    fields = ["user", "is_owner", "is_active"]


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "ruc", "country", "is_active", "created_at"]
    search_fields = ["name", "legal_name", "slug", "ruc"]
    list_filter = ["is_active", "country"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [MembershipInline]


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "is_owner", "is_active"]
    list_filter = ["is_owner", "is_active"]
    search_fields = ["user__email", "tenant__name"]
    autocomplete_fields = ["user", "tenant"]
