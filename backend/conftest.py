import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.core.tenancy import tenant_context
from apps.iam.models import Role
from apps.iam.services import create_default_roles, set_member_roles
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
def roles(tenant: Tenant) -> dict[str, Role]:
    return {r.name: r for r in create_default_roles(tenant)}


def make_member(tenant: Tenant, email: str, role_names: list[str], roles: dict) -> User:
    """Crea un usuario no propietario con los roles indicados."""
    member = User.objects.create_user(email, PASSWORD)
    m = Membership.objects.create(user=member, tenant=tenant)
    with tenant_context(tenant):
        set_member_roles(m, [roles[n] for n in role_names])
    return member


def client_for(user: User, tenant: Tenant | None = None) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    if tenant is not None:
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}",
            HTTP_X_TENANT_ID=str(tenant.pk),
        )
    return client


@pytest.fixture
def owner_api(user: User, tenant: Tenant, membership: Membership, roles) -> APIClient:
    """Cliente del propietario con la empresa activa."""
    return client_for(user, tenant)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_api(user: User) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client
