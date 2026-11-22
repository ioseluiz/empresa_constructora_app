from rest_framework.routers import SimpleRouter

from .views import (
    AssignmentViewSet,
    ContractViewSet,
    DocumentViewSet,
    EmployeeViewSet,
    SalaryRecordViewSet,
)

router = SimpleRouter()
router.register("employees", EmployeeViewSet, basename="employee")
router.register("contracts", ContractViewSet, basename="contract")
router.register("salaries", SalaryRecordViewSet, basename="salary")
router.register("assignments", AssignmentViewSet, basename="assignment")
router.register("documents", DocumentViewSet, basename="document")
urlpatterns = router.urls
