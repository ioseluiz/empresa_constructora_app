from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ConsolidatedView,
    LegalParameterViewSet,
    PayrollConceptViewSet,
    PayrollRunViewSet,
    PayrollSettingsView,
    PayslipViewSet,
    PreviewView,
    RecurringDeductionViewSet,
    SipeReportView,
)

router = SimpleRouter()
router.register("legal-parameters", LegalParameterViewSet, basename="legal-parameter")
router.register("concepts", PayrollConceptViewSet, basename="payroll-concept")
router.register("deductions", RecurringDeductionViewSet, basename="recurring-deduction")
router.register("runs", PayrollRunViewSet, basename="payroll-run")
router.register("payslips", PayslipViewSet, basename="payslip")
urlpatterns = [
    path("settings/", PayrollSettingsView.as_view(), name="payroll-settings"),
    path("preview/", PreviewView.as_view(), name="payroll-preview"),
    path("consolidated/", ConsolidatedView.as_view(), name="payroll-consolidated"),
    path("reports/sipe/", SipeReportView.as_view(), name="payroll-sipe"),
    *router.urls,
]
