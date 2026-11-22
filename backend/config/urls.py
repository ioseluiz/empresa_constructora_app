from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.iam.urls import public_urlpatterns as invitation_urls

api_v1: list[URLPattern | URLResolver] = [
    path("", include("apps.core.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("auth/invitations/", include(invitation_urls)),
    path("tenant/", include("apps.tenants.urls")),
    path("iam/", include("apps.iam.urls")),
    path("audit/", include("apps.audit.urls")),
    path("org/", include("apps.organization.urls")),
    path("projects/", include("apps.projects.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
]
