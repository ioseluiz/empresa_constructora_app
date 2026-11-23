from rest_framework.routers import SimpleRouter

from .views import (
    ClockCodeViewSet,
    DeviceViewSet,
    ImportBatchViewSet,
    ImportTemplateViewSet,
    PunchViewSet,
)

router = SimpleRouter()
router.register("devices", DeviceViewSet, basename="device")
router.register("clock-codes", ClockCodeViewSet, basename="clock-code")
router.register("templates", ImportTemplateViewSet, basename="import-template")
router.register("batches", ImportBatchViewSet, basename="import-batch")
router.register("punches", PunchViewSet, basename="punch")
urlpatterns = router.urls
