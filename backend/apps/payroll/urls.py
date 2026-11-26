from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ConsolidatedView,
    LegalParameterViewSet,
    PayrollConceptViewSet,
    PayrollRunViewSet,
    PayrollSettingsView,
    PreviewView,
    RecurringDeductionViewSet,
)

router = SimpleRouter()
router.register("legal-parameters", LegalParameterViewSet, basename="legal-parameter")
router.register("concepts", PayrollConceptViewSet, basename="payroll-concept")
router.register("deductions", RecurringDeductionViewSet, basename="recurring-deduction")
router.register("runs", PayrollRunViewSet, basename="payroll-run")
urlpatterns = [
    path("settings/", PayrollSettingsView.as_view(), name="payroll-settings"),
    path("preview/", PreviewView.as_view(), name="payroll-preview"),
    path("consolidated/", ConsolidatedView.as_view(), name="payroll-consolidated"),
    *router.urls,
]
