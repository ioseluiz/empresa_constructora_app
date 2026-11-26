from django.contrib import admin

from .models import LegalParameter


@admin.register(LegalParameter)
class LegalParameterAdmin(admin.ModelAdmin):
    """Los parámetros legales son globales: los mantiene el operador de la plataforma."""

    list_display = ["country", "key", "name", "value", "valid_from"]
    list_filter = ["country", "key"]
    search_fields = ["key", "name"]
