from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("cost-centers", views.CostCenterViewSet, basename="cost-center")
router.register("positions", views.PositionViewSet, basename="position")
router.register("cba-categories", views.CBACategoryViewSet, basename="cba-category")
router.register("cba-rates", views.CBAWageRateViewSet, basename="cba-rate")
router.register("holidays", views.HolidayViewSet, basename="holiday")
urlpatterns = router.urls
