from django.apps import AppConfig


class PayrollPaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.payroll_pa"
    verbose_name = "Planilla · Panamá"

    def ready(self) -> None:
        from apps.payroll.rules import register

        from .rules import PanamaRules

        register("PA", PanamaRules())
