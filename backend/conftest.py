import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.tenants.models import Membership, Tenant

PASSWORD = "Contraseña-Segura-2026"  # noqa: S105


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user("ana@constructora.pa", PASSWORD, first_name="Ana")


@pytest.fixture
def tenant(db) -> Tenant:
    return Tenant.objects.create(name="Constructora Istmo", slug="istmo", ruc="155-1-2026")


@pytest.fixture
def other_tenant(db) -> Tenant:
    return Tenant.objects.create(name="Obras del Pacífico", slug="pacifico")


@pytest.fixture
def membership(user: User, tenant: Tenant) -> Membership:
    return Membership.objects.create(user=user, tenant=tenant, is_owner=True)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_api(user: User) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client
