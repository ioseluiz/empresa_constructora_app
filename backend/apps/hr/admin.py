from django.contrib import admin

from apps.iam.admin import AllTenantsAdmin

from .models import Employee, EmploymentContract


@admin.register(Employee)
class EmployeeAdmin(AllTenantsAdmin):
    list_display = ["code", "first_name", "last_name", "id_number", "status", "tenant"]
    list_filter = ["status"]
    search_fields = ["code", "first_name", "last_name", "id_number"]


@admin.register(EmploymentContract)
class EmploymentContractAdmin(AllTenantsAdmin):
    list_display = ["employee", "contract_type", "start_date", "end_date", "status", "tenant"]
    list_filter = ["status", "contract_type"]
