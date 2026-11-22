from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("roles", views.RoleViewSet, basename="role")
router.register("members", views.MemberViewSet, basename="member")
router.register("invitations", views.InvitationViewSet, basename="invitation")

urlpatterns = [
    path("me/", views.MyAccessView.as_view(), name="iam-me"),
    path("permissions/", views.PermissionCatalogView.as_view(), name="iam-permissions"),
    *router.urls,
]

public_urlpatterns = [
    path("<str:token>/", views.InvitationPublicView.as_view(), name="invitation-public"),
    path("<str:token>/accept/", views.InvitationAcceptView.as_view(), name="invitation-accept"),
]
