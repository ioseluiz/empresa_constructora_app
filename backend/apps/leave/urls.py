from rest_framework.routers import SimpleRouter

from .views import BalanceViewSet, VacationAdjustmentViewSet, VacationRequestViewSet

router = SimpleRouter()
router.register("vacations", VacationRequestViewSet, basename="vacation")
router.register("adjustments", VacationAdjustmentViewSet, basename="vacation-adjustment")
router.register("balances", BalanceViewSet, basename="vacation-balance")
urlpatterns = router.urls
