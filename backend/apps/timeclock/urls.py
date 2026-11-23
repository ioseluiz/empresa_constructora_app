from rest_framework.routers import SimpleRouter

from .views import (
    ClockCodeViewSet,
    DeviceViewSet,
    ImportBatchViewSet,
    ImportTemplateViewSet,
    PunchViewSet,
    ShiftAssignmentViewSet,
    ShiftViewSet,
    WorkDayViewSet,
)

router = SimpleRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("clock-codes", ClockCodeViewSet, basename="clock-code")
router.register("templates", ImportTemplateViewSet, basename="import-template")
router.register("batches", ImportBatchViewSet, basename="import-batch")
router.register("punches", PunchViewSet, basename="punch")
router.register("shifts", ShiftViewSet, basename="shift")
router.register("shift-assignments", ShiftAssignmentViewSet, basename="shift-assignment")
router.register("workdays", WorkDayViewSet, basename="workday")
urlpatterns = router.urls
